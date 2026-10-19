# Preserve the exact production DOMjudge version and add FPC to its build sandbox.
FROM domjudge/judgehost@sha256:24304474590c5a62c5395589407ce8a996e7dd694832d24a29d2eb0014e15da5
USER root
RUN cp /etc/resolv.conf /chroot/domjudge/etc/resolv.conf \
    && chroot /chroot/domjudge /bin/sh -c 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends fp-compiler fp-units-rtl && apt-get clean && rm -rf /var/lib/apt/lists/*' \
    && chroot /chroot/domjudge /usr/bin/fpc -iV
COPY prepare.php run-testlib /opt/domjudge/judgehost/lib/judge/pascal/
COPY vendor/ /opt/domjudge/judgehost/lib/judge/pascal/vendor/
