# IPE sandbox baseline image — DockerRunner (T1)이 docker run으로 호출.
#
# Build: docker build -t ipe-sandbox:latest .
# Run:   DockerRunner는 cmd/cwd/limits를 동적으로 주입.
#
# Python 3.11 + JDK 17 (P3+에서 Solution.java 컴파일에 필요).

FROM python:3.11-slim

# Java for solution.java compilation (P3+에서 사용 예정)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# 비특권 사용자로 실행 (read-only rootfs와 함께 보안 layer)
USER nobody:nogroup

# DockerRunner는 --workdir flag로 임의 경로 지정 가능. /work는 일반 default.
WORKDIR /work
