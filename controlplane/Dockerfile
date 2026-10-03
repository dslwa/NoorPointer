FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY controlplane/pom.xml controlplane/pom.xml
RUN mvn -B -ntp -f controlplane/pom.xml dependency:resolve
COPY controlplane/src controlplane/src
COPY dashboard/index.html dashboard/app.js dashboard/styles.css dashboard/favicon.svg dashboard/
RUN mvn -B -ntp -f controlplane/pom.xml package -DskipTests

FROM eclipse-temurin:21-jre-alpine
RUN apk add --no-cache curl && addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=build --chown=app:app /workspace/controlplane/target/control-plane-0.1.0.jar app.jar
USER app
ENV SERVER_ADDRESS=0.0.0.0 PORT=8082
EXPOSE 8082
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 CMD curl --fail --silent http://127.0.0.1:8082/actuator/health || exit 1
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
