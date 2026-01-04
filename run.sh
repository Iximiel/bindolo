#!/bin/bash

source ./venv/bin/activate

uwsgi bindolo.ini
