cmake_minimum_required(VERSION 3.10)
project(PipelineOCR)

# Vérifier que Docker est installé
find_program(DOCKER_EXEC docker)

if(NOT DOCKER_EXEC)
    if(WIN32)
        set(INSTALL_URL "https://docs.docker.com/desktop/install/windows-install/")
    elseif(APPLE)
        set(INSTALL_URL "https://docs.docker.com/desktop/install/mac-install/")
    elseif(UNIX)
        set(INSTALL_URL "https://docs.docker.com/engine/install/")
    endif()

    message(FATAL_ERROR
        "❌ Docker n'est pas installé ou non trouvé dans le PATH.\n"
        "👉 Installez-le ici : ${INSTALL_URL}")
endif()

message(STATUS "✅ Docker détecté : ${DOCKER_EXEC}")

# Appeler Make automatiquement après configuration
message(STATUS "🛠️  Vous pouvez maintenant exécuter : make build ou make run")