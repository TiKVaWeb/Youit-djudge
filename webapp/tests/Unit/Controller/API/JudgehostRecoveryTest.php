<?php declare(strict_types=1);

namespace App\Tests\Unit\Controller\API;

use App\Controller\API\JudgehostController;
use App\Entity\Contest;
use App\Entity\Judgehost;
use App\Entity\JudgeTask;
use App\Entity\Judging;
use App\Entity\JudgingRun;
use App\Entity\QueueTask;
use App\Entity\Submission;
use App\Entity\Team;
use App\Service\BalloonService;
use App\Service\ConfigurationService;
use App\Service\DOMJudgeService;
use App\Service\EventLogService;
use App\Service\RejudgingService;
use App\Service\ScoreboardService;
use App\Service\SubmissionService;
use Doctrine\Common\Collections\ArrayCollection;
use Doctrine\DBAL\Connection;
use Doctrine\DBAL\Result;
use Doctrine\ORM\EntityManagerInterface;
use Doctrine\ORM\EntityManager;
use Doctrine\ORM\EntityRepository;
use Doctrine\ORM\Query;
use Doctrine\ORM\QueryBuilder;
use PHPUnit\Framework\TestCase;
use Psr\Log\NullLogger;
use Symfony\Component\HttpFoundation\Request;

class RecoveryProbe extends JudgehostController
{
    public bool $recordOnly = false;
    public array $recovered = [];

    public function recover(int $id, Judgehost $host): void
    {
        $this->giveBackJudging($id, $host);
    }

    protected function giveBackJudging(int $judgingId, ?Judgehost $judgehost): void
    {
        if ($this->recordOnly) {
            $this->recovered[] = $judgingId;
            return;
        }
        parent::giveBackJudging($judgingId, $judgehost);
    }
}

class JudgehostRecoveryTest extends TestCase
{
    private function controller(EntityManagerInterface $em): RecoveryProbe
    {
        return new RecoveryProbe(
            $em, $this->createMock(DOMJudgeService::class),
            $this->createMock(ConfigurationService::class), $this->createMock(EventLogService::class),
            $this->createMock(ScoreboardService::class), $this->createMock(SubmissionService::class),
            $this->createMock(BalloonService::class), $this->createMock(RejudgingService::class),
            new NullLogger()
        );
    }

    private function judging(array $runs, ?float $endtime = null, bool $complete = false): Judging
    {
        $contest = $this->createMock(Contest::class);
        $contest->method('getCid')->willReturn(1);
        $submission = $this->createMock(Submission::class);
        $submission->method('getTeam')->willReturn(new Team());
        $submission->method('getSubmittime')->willReturn(100.0);
        $submission->method('getSubmitid')->willReturn(7);
        $judging = $this->createMock(Judging::class);
        $judging->method('getJudgingid')->willReturn(10);
        $judging->method('getRuns')->willReturn(new ArrayCollection($runs));
        $judging->method('getSubmission')->willReturn($submission);
        $judging->method('getContest')->willReturn($contest);
        $judging->method('getEndtime')->willReturn($endtime);
        $judging->method('getJudgeCompletely')->willReturn($complete);
        return $judging;
    }

    public function testRegistrationIncludesNullResultsAndExcludesInvalidTasks(): void
    {
        $em = $this->createMock(EntityManager::class);
        $host = (new Judgehost())->setHostname('judgedaemon-0-0');
        $judging = $this->judging([]);
        $query = $this->createMock(Query::class);
        $query->method('getOneOrNullResult')->willReturn($host);
        $query->method('getResult')->willReturn([$judging]);
        $builder = $this->createMock(QueryBuilder::class);
        foreach (['from', 'select', 'leftJoin', 'innerJoin', 'setParameter', 'setMaxResults', 'distinct'] as $method) {
            $builder->method($method)->willReturnSelf();
        }
        $conditions = [];
        $builder->method('andWhere')->willReturnCallback(function ($condition) use (&$conditions, $builder) {
            $conditions[] = $condition;
            return $builder;
        });
        $builder->method('getQuery')->willReturn($query);
        $em->method('createQueryBuilder')->willReturn($builder);
        $controller = $this->controller($em);
        $controller->recordOnly = true;
        $controller->createJudgehostAction(new Request([], ['hostname' => 'judgedaemon-0-0']));
        self::assertContains('(j.result IS NULL OR j.result != :compiler_error)', $conditions);
        self::assertContains('(j.endtime IS NULL OR j.judgeCompletely = 1)', $conditions);
        self::assertContains('jt.valid = 1', $conditions);
        self::assertSame([10], $controller->recovered);
    }

    /** @dataProvider recoveryCases */
    public function testReturnedTasksRestoreQueueWithoutTouchingCompletedRuns(
        bool $existingQueue, bool $valid, bool $finished, bool $otherHost, ?float $endtime, bool $complete
    ): void {
        $host = (new Judgehost())->setHostname('judgedaemon-0-0');
        $task = (new JudgeTask())->setJudgehost($otherHost ? (new Judgehost())->setHostname('other') : $host)
            ->setStarttime(100.0)->setPriority(-10)->setValid($valid);
        $run = (new JudgingRun())->setJudgeTask($task);
        if ($finished) {
            $run->setRunresult('correct');
        }
        $judging = $this->judging([$run], $endtime, $complete);
        $queue = $existingQueue ? (new QueueTask())->setStartTime(100.0) : null;
        $judgingRepository = $this->createMock(EntityRepository::class);
        $judgingRepository->method('find')->willReturn($judging);
        $queueRepository = $this->createMock(EntityRepository::class);
        $queueRepository->method('findOneBy')->willReturn($queue);
        $connection = $this->createMock(Connection::class);
        $result = $this->createMock(Result::class);
        $result->method('fetchOne')->willReturn(10);
        $connection->expects(self::exactly(2))->method('executeQuery')
            ->with('SELECT judgingid FROM judging WHERE judgingid = :id FOR UPDATE', ['id' => 10])
            ->willReturn($result);
        $em = $this->createMock(EntityManager::class);
        $em->method('getConnection')->willReturn($connection);
        $em->method('getRepository')->willReturnCallback(
            fn($class) => $class === Judging::class ? $judgingRepository : $queueRepository
        );
        $em->method('wrapInTransaction')->willReturnCallback(fn($work) => $work());
        $persisted = [];
        $em->method('persist')->willReturnCallback(function ($entity) use (&$persisted) {
            $persisted[] = $entity;
        });
        $controller = $this->controller($em);
        $controller->recover(10, $host);
        $controller->recover(10, $host);
        $eligible = $valid && !$finished && !$otherHost && ($endtime === null || $complete);
        self::assertCount($eligible && !$existingQueue ? 1 : 0, $persisted);
        self::assertSame($eligible ? null : 100.0, $task->getStarttime());
        if ($eligible) {
            $restored = $queue ?? $persisted[0];
            self::assertNull($restored->getStartTime());
            if (!$existingQueue) {
                self::assertSame(-10, $restored->getPriority());
            }
        }
        self::assertSame($finished ? 'correct' : null, $run->getRunresult());
    }

    public function recoveryCases(): iterable
    {
        yield 'lost queue' => [false, true, false, false, null, false];
        yield 'existing queue' => [true, true, false, false, null, false];
        yield 'invalid task' => [false, false, false, false, null, false];
        yield 'completed run' => [false, true, true, false, null, false];
        yield 'another host' => [false, true, false, true, null, false];
        yield 'completed judging' => [false, true, false, false, 200.0, false];
        yield 'explicit remaining tests' => [false, true, false, false, 200.0, true];
    }

    public function testEmptyBatchRechecksReturnedTasksUnderTheSameJudgingLock(): void
    {
        $query = $this->createMock(Query::class);
        $query->method('getResult')->willReturn([]);
        $builder = $this->createMock(QueryBuilder::class);
        foreach (['from', 'select', 'andWhere', 'setParameter', 'setMaxResults', 'addOrderBy'] as $method) {
            $builder->method($method)->willReturnSelf();
        }
        $builder->method('getQuery')->willReturn($query);
        $result = $this->createMock(Result::class);
        $result->method('fetchOne')->willReturn(10);
        $connection = $this->createMock(Connection::class);
        $connection->expects(self::once())->method('executeQuery')
            ->with('SELECT judgingid FROM judging WHERE judgingid = :jobid FOR UPDATE', ['jobid' => 10])
            ->willReturn($result);
        $connection->expects(self::once())->method('executeStatement')
            ->with(self::callback(fn($sql) => str_contains($sql, 'AND NOT EXISTS (')
                && str_contains($sql, 'AND judgehostid IS NULL AND type = :type)')),
                ['jobid' => 10, 'type' => 'judging_run'])
            ->willReturn(0);
        $connection->method('transactional')->willReturnCallback(fn($work) => $work($connection));
        $em = $this->createMock(EntityManager::class);
        $em->method('getConnection')->willReturn($connection);
        $em->method('createQueryBuilder')->willReturn($builder);
        $controller = $this->controller($em);
        $method = new \ReflectionMethod(JudgehostController::class, 'getJudgetasks');
        self::assertNull($method->invoke($controller, 10, 5, (new Judgehost())->setHostname('host')));
    }
}
