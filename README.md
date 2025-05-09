EN

Step 1: Download the image
First, pull the Docker image:
  docker pull noered2/selenium-runner:latest

Step 2: Initialize Docker Swarm
Start Docker Swarm to gain access to the Docker Secrets module:

Step 3: Set Docker Secrets
  docker swarm init

Create the Docker Secrets for your instance, including the values for sn_url, sn_user and sn_password. For example, for the password:

  echo “ServiceNow password” | docker secret create sn_password -
Repeat the process for sn_user and sn_url by setting the corresponding values for these secrets.

Step 4: Start the service
Create and start the Docker service with the secrets:

docker service create \
  --name selenium-service \
  --secret sn_password \
  --secret sn_user \
  --secret sn_url \
  noered2/selenium-runner:latest

DE

Schritt 1: Image herunterladen
Zuerst ziehst du das Docker-Image:
  docker pull noered2/selenium-runner:latest

Schritt 2: Docker Swarm initialisieren
Starte Docker Swarm, um Zugriff auf das Docker Secrets-Modul zu erhalten:

Schritt 3: Docker-Secrets festlegen
  docker swarm init

Erstelle die Docker-Secrets für deine Instanz, einschließlich der Werte für sn_url, sn_user und sn_password. Zum Beispiel für das Passwort:

  echo "ServiceNow password" | docker secret create sn_password -
Wiederhole den Vorgang für sn_user und sn_url, indem du die entsprechenden Werte für diese Secrets festlegst.

Schritt 4: Service starten
Erstelle und starte den Docker-Service mit den Secrets:

docker service create \
  --name selenium-service \
  --secret sn_password \
  --secret sn_user \
  --secret sn_url \
  noered2/selenium-runner:latest
