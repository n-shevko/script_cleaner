import os
import json
import subprocess
import traceback


def docker_exists():
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if "Docker version" in result.stdout:
            return True
        else:
            return False
    except FileNotFoundError:
        return False


def docker(volumes, cmd, name=None):
    try:
        volumes = ' '.join([f'-v {host}:{container}' for host, container in volumes])
        if name:
            name = f' --name {name} '
        else:
            name = ''
        full_cmd = f'docker run --rm {name} {volumes} ghcr.io/ggerganov/whisper.cpp:main "{cmd}"'
        return os.system(full_cmd)
    except Exception as e:
        print(str(e) + '\n' + traceback.format_exc())
        return -1


current_directory = os.path.dirname(os.path.abspath(__file__))


def write_config(config):
    with open(os.path.join(current_directory, 'config.json'), 'w') as f:
        f.write(json.dumps(config, indent=2))