cmake_minimum_required(VERSION 3.10)
project(OCR_pipeline)

find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

# Installation des dépendances Python
execute_process(COMMAND ${Python3_EXECUTABLE} -m pip install -r ${CMAKE_SOURCE_DIR}/requirements.txt)