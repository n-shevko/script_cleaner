import os
import json

from utils import docker_exists, docker


def install():
    if not docker_exists():
        print("Install docker first https://docs.docker.com/desktop/install/mac-install/")
        return

    current_directory = os.path.dirname(os.path.abspath(__file__))
    response = docker([(current_directory, '/models')], './models/download-ggml-model.sh base.en /models')
    if response == 0:
        print('Installed successfully')
    else:
        print("Can't download audio recognition model")
        return

    api_key = input("Paste your OpenAI API key and press enter:")
    template = os.path.join(current_directory, 'config_template.json')
    with open(template, 'r') as f:
        config = json.loads(f.read())
    config['chatgpt_api_key'] = api_key

    with open(os.path.join(current_directory, 'config.json'), 'w') as f:
        f.write(json.dumps(config, indent=2))

    print('Installed successfully.\nNow you can run command: python3 main.py')

install()