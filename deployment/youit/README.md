# Перенос серверных доработок YouIT — 19.10.2026

Это сохранение существующей конфигурации, **не инструкция запускать её целиком**.
Активные сервисы, БД, данные и таймеры при переносе не изменялись.

## Состав и происхождение

`server-patches.sha256.json` содержит серверный путь, путь в форке и SHA-256
каждого из 29 скопированных файлов. Хеши вычислены повторно на сервере после
копирования. Native PHP-файлы форка совпадают с активными read-only overrides.
Pascal runtime-файлы дополнительно сверены с файлами внутри рабочего образа.

| Компонент | Что сохранено |
| --- | --- |
| Импорт задач | MIME-only `finfo`, ограничение display-type вложения четырьмя символами |
| Event-feed | Пакетный просмотр ID, ограниченная загрузка событий, detach, keepalive, сохранение курсора и проверок gaps |
| Judgehost | Pascal, C++23 при сборке executable, очистка производного testcase-кеша при нехватке места |
| Pascal | Компилятор в build chroot, выбор entrypoint, классический testlib, протокольный адаптер, лицензия и синтетические тесты |
| Upgrade | `DOMJUDGE_SKIP_REFRESH_CACHE_ON_UPGRADE`, исходный `.in` и точный установленный скрипт |
| PHP-FPM/nginx | Основной пул 6, feed-пул 8, таймауты, upload/post limits, startup hook |
| Обслуживание | Четыре скрипта и четыре пары systemd service/timer, включая cleanup compiled-checker cache |
| Compose | Все шесть сервисов, mounts, logging, healthchecks, ограничения, сеть и настройки MariaDB; без паролей |

`pascal/Dockerfile`, `pascal/README.md`, `pascal/pascal-executables.patch` — точные
архивные файлы прежней поставки, не новый способ сборки. Старый patch уже
применён к `judge/judgedaemon.main.php`; повторно применять его не нужно.
Для Git-сборки `judge/Makefile` теперь устанавливает Pascal runtime в LIBJUDGEDIR.

Старые резервные копии overrides, журналы, кеши, одноразовые скрипты коррекции
инцидентов и выгрузки реальных тестов намеренно исключены. Изменения языков,
задач, special_run/checker associations и других записей БД — данные, а не патчи
исходников. БД не экспортировалась и остаётся на сервере; для миграции системы
целиком отдельно необходим проверяемый backup этих данных.

## Зафиксированные образы

- Domserver base: `domjudge/domserver@sha256:60660ca92ce3762e76834b49a3581c54d72ba956c698653f427582b7b1a50a5c`;
  локальный image ID: `sha256:0a6b4449a048bc3b4110a18791d378d60bcef76f1587a5f61f6c6e39fedb412c`.
- Judgehost base: `domjudge/judgehost@sha256:24304474590c5a62c5395589407ce8a996e7dd694832d24a29d2eb0014e15da5`.
- Рабочий Pascal image ID всех четырёх judgehost:
  `sha256:aaad85cea071011dd054734538bd50234b3948e2bf6ef5b47d9b512bf826a744`.
- MariaDB reference сохранён в снимке Compose. Обновление БД/образов не выполнялось.

Image ID не равен registry digest. Новая сборка может получить другой digest:
FPC устанавливается из apt, версии пакетов и содержимое репозитория могут меняться.
Dockerfile сохраняет рецепт, но не обещает побайтовое воспроизведение старого образа.

## Сборка совместимых образов

Из корня репозитория, на отдельном Linux build-хосте:

```sh
docker build --platform linux/amd64 -f deployment/youit/Dockerfile.domserver -t youit-domserver:local .
docker build --platform linux/amd64 -f deployment/youit/Dockerfile.judgehost -t youit-judgehost:local .
```

Это compatibility overlay на закреплённые production bases, не полная сборка
всего DOMjudge из Git. В domserver включены также FPM/nginx/hook и установленный
скрипт upgrade. В judgehost включены daemon, Pascal runtime и FPC в chroot.
Полная исходная сборка остаётся штатной по `doc/manual/develop.rst` и отдельно
требует установки FPC в build chroot и переноса deployment-конфигурации.

Снимок `compose.production.snapshot.json` содержит **старые абсолютные пути**
mounts на сервере и имя существующего database volume. Он предназначен для
сверки, не для запуска на Mac или поверх production. В новых образах патчи уже
внутри; старые bind mounts могут скрыть новые файлы. Удалять/менять их можно
только при отдельном подготовленном rollout, по одному judgehost.

Пароли заменены обязательными `${VARIABLE:?…}`. Их передают вне Git. Пример
проверки структуры без настоящих секретов и без запуска контейнеров:

```sh
MYSQL_PASSWORD=validation-only MYSQL_ROOT_PASSWORD=validation-only JUDGEDAEMON_PASSWORD=validation-only \
  docker compose -f deployment/youit/compose.production.snapshot.json config --quiet
```

## Проверки

```sh
python3 -m unittest discover -s deployment/youit/tests -v
python3 -m unittest discover -s deployment/youit/maintenance -p test_cleanup.py -v
php -l judge/judgedaemon.main.php
php -l webapp/src/Controller/API/ContestController.php
php -l webapp/src/Service/ImportProblemService.php
```

Первая группа проверяет 29 хешей, upgrade template, установку Pascal,
подготовку Pascal executable и синтетические exit codes адаптера.
Вторая использует только fake DB/Docker и проверяет cleanup, включая
сохранение busy/disabled/last host и возврат host после ошибки.
`judge/pascal/test.php` — дополнительные реальные FPC compilation/protocol tests;
запускать в изолированном контейнере без сети и доступа к БД/рабочим judgings.
Полный PHPUnit DOMjudge, полная исходная сборка и сквозное тестирование новых
образов с отдельной БД — отдельные проверки перед будущим релизом. Фактически
выполненные проверки compatibility-образов перечислены в `VALIDATION.md`.

## Важные ограничения существующего обслуживания

Не включать таймеры автоматически при клонировании форка.

- `domjudge-clean-judgehost-cache` отключает и останавливает один idle host,
  удаляет только его производные testcase/executable caches, восстанавливает host.
- `domjudge-clean-judgehost-workdirs.sh` удаляет numeric workdirs только по возрасту,
  **без проверки активной работы в БД**. Скрипт сохранён без изменения поведения;
  перед новым внедрением нужна отдельная доработка защиты долгих проверок.
- `domjudge-retention` удаляет старые invalid judgetask rows; каскадные зависимости
  могут затрагивать подробности старых запусков. Это не безусловно безопасная
  операция «без потери данных». Перед включением проверить схему и retention policy.
- `domjudge-clean-runtime-logs.sh` обнуляет большие operational/Docker logs и
  сокращает journald. Такие журналы после очистки без backup не восстановить.

На сервере уже был один restart у judgehost-3. Перенос патчей не изменяет этот
исторический счётчик и не выдаётся за исправление всех эксплуатационных проблем.
