# Результаты переноса — 19.10.2026

## Что проверено

- 29 файлов форка совпадают побайтно с повторно вычисленными серверными SHA-256.
- Активные mounted PHP overrides domserver и daemon во всех четырёх judgehost
  соответствуют скопированным файлам; Pascal runtime внутри рабочего образа
  совпадает с сохранённой поставкой.
- 9 offline tests: manifest, обязательные подстановки секретов в Compose,
  эквивалентность `.in` установленному upgrade script, Makefile installation,
  Pascal entrypoint/fallback/quoting/units и адаптер кодов завершения.
- 10 fake DB/Docker cleanup tests: expired/fresh testcase и executable cache,
  busy/disabled/last host, dry-run, race, восстановление при ошибке остановки.
- 24 реальных Pascal compilation/protocol cases прошли дважды: сначала на
  отдельном временном контейнере из текущего production judgehost image, затем
  на локально собранном новом compatibility image. Оба запуска без сети,
  под UID 65534, без capabilities, с read-only rootfs, отдельным tmpfs и лимитами.
  Production БД, задачи, данные учеников и рабочие judgings не подключались.
- FPC 3.2.2 подтверждён внутри chroot нового judgehost image.
- PHP syntax проверки всех перенесённых PHP-файлов прошли; ключевые файлы также
  проверены PHP внутри соответствующих образов, а не только локальным PHP 8.5.
- Shell syntax и `docker compose config --quiet` с тестовыми placeholders прошли.
- PHP-FPM и nginx конфигурация действующего domserver валидна; PHP-FPM нового
  локального образа также прошёл проверку конфигурации.
- Значения реальных production secrets из Compose проверены на отсутствие во
  всех файлах репозитория перед публикацией. Сами секреты в отчёт не включены.
- Проверка whitespace прошла с исключением только `judge/pascal/vendor/testlib.pas`:
  его исходные trailing spaces намеренно сохранены ради побайтового соответствия.

## Локально собранные образы

Оба построены через Dockerfile из `deployment/youit`, платформа linux/amd64:

| Локальный тег | ID, показанный локальным Docker |
| --- | --- |
| `youit-domserver:fork-patches-20261019` | `sha256:5ac86a9cd7d23ed82bb9c9ed075418f3dea267b676d6280008333cd40f3a97dd` |
| `youit-judgehost:fork-patches-20261019` | `sha256:5d3064e9728819b65cc92ff7ffcb547f79e41812b1f5ed0b69bf0971a6926947` |

Образы не отправлялись в registry и не выкатывались. Это compatibility overlays
на закреплённые bases, не доказательство полной исходной сборки DOMjudge.

## Ограничения и существующие предупреждения

- Полный PHPUnit с тестовой БД и сквозной приём/проверка посылки через новый
  domserver + judgehost не выполнялись. Новые образы не подключались к production.
- Полная сборка native DOMjudge с configure/make не выполнялась; Makefile
  installation Pascal проверена статически. Нативная sandbox/cgroup интеграция
  нового образа потребует выделенного Linux-стенда.
- В исходном production base domserver есть предупреждение PHP о несовместимом
  `ds.so` (`undefined symbol: fast_add_function`). Оно наблюдается и на сервере,
  и в новом compatibility image, не внесено переносом и здесь не исправлялось.
  PHP syntax/FPM config проверки завершаются успешно несмотря на предупреждение.
- Сохранены существующие риски maintenance scripts, описанные в `README.md`;
  дополнительная очистка и retention при проверках не запускались.
- Manifest фиксирует baseline переноса. Намеренные будущие изменения этих файлов
  нужно сопровождать новым аудитом/версией проверки, не подменяя исторические
  серверные хеши утверждением, будто новые байты уже были на сервере.

## Production после проверки

Рабочие domserver, MariaDB и четыре judgehost остались running; StartedAt и
RestartCount совпали со снимком до переноса. У judgehost-3 уже был один restart;
его счётчик не сбрасывался. Временный тестовый контейнер удалён автоматически,
временные синтетические тестовые файлы на сервере удалены отдельно.
Секреты, данные уроков, задачи, посылки, результаты и БД не изменялись.
