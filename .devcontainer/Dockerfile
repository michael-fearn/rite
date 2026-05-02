FROM debian:13

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

# Install the project toolchain via the same script used by CI runners.
# Anything platform-shared belongs in install-toolchain.sh, not here.
COPY scripts/setup/install-toolchain.sh /tmp/install-toolchain.sh
RUN bash /tmp/install-toolchain.sh \
 && rm /tmp/install-toolchain.sh

# Non-root dev user with bash login shell + passwordless sudo (devcontainer norm).
RUN groupadd --gid "${USER_GID}" "${USERNAME}" \
 && useradd --uid "${USER_UID}" --gid "${USER_GID}" \
      --create-home --shell /bin/bash "${USERNAME}" \
 && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/"${USERNAME}" \
 && chmod 0440 /etc/sudoers.d/"${USERNAME}"

USER ${USERNAME}
WORKDIR /workspaces/fortress2
SHELL ["/bin/bash", "-c"]
ENV SHELL=/bin/bash

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sleep", "infinity"]
