# Jenkins for the end-to-end suite.
#
# Digest-pinned, not tag-pinned: `2.580.1-lts-jdk21` is the tag this digest
# carried when it was recorded, but a tag can be repointed and a digest cannot.
# The index is multi-arch (linux/amd64 and linux/arm64), so this builds on CI
# runners and Apple Silicon alike.
#
# To bump, resolve the new digest and re-check plugins.txt against it:
#   container image pull jenkins/jenkins:<tag> && container images ls
FROM jenkins/jenkins@sha256:a660310e39ade10631f774bacd5219de767dfd08947ea5c32a739b5e5bb382c1

# No setup wizard: the instance is configured declaratively instead, so a
# first boot is reproducible rather than interactive.
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"

# Where the Configuration-as-Code plugin looks on startup.
ENV CASC_JENKINS_CONFIG=/var/jenkins_home/casc.yaml

# Baked at build time so boot does not depend on the update centre being
# reachable — a test suite that fails because plugins.jenkins.io is having a
# bad morning is a test suite nobody trusts.
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# The admin credentials are fixed and well known. That is deliberate: this
# instance is unreachable from outside the test host and is destroyed with the
# session. Never point this image at anything real.
COPY casc.yaml /var/jenkins_home/casc.yaml
