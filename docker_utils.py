import json
import random
import uuid
from collections import OrderedDict

import docker
from .db_utils import DBUtils
from .models import DynamicDockerChallenge


class DockerUtils:

    @staticmethod
    def add_new_docker_container(user_id, challenge_id, flag, port):
        configs = DBUtils.get_all_configs()

        dynamic_docker_challenge = DynamicDockerChallenge.query \
            .filter(DynamicDockerChallenge.id == challenge_id) \
            .first_or_404()

        client = docker.DockerClient(base_url=configs.get("docker_api_url"))
        in_port = dynamic_docker_challenge.redirect_port
        ports = {str(in_port):str(port)}
        uuid_code = str(uuid.uuid4())

        try:
            client.containers.run(image=dynamic_docker_challenge.docker_image, name=str(user_id) + '-' + uuid_code,
                              environment={'FLAG': flag}, detach=True,
                              mem_limit=dynamic_docker_challenge.memory_limit,
                              nano_cpus=int(dynamic_docker_challenge.cpu_limit * 1e9), auto_remove=True, ports=ports)
            DBUtils.create_new_container(user_id, challenge_id, flag, uuid_code, port)
            return True
        except:
            DBUtils.remove_current_container(user_id)
            DockerUtils.remove_current_docker_container(user_id)
            return False
        
            
    @staticmethod
    def remove_current_docker_container(user_id, is_retry=False):
        configs = DBUtils.get_all_configs()
        container = DBUtils.get_current_containers(user_id=user_id)

        auto_containers = configs.get("docker_auto_connect_containers", "").split(",")

        if container is None:
            return

        try:
            client = docker.DockerClient(base_url=configs.get("docker_api_url"))
            networks = client.networks.list(names=[str(user_id) + '-' + container.uuid])

            if len(networks) == 0:
                containers = client.containers.list(filters={'name': str(user_id) + '-' + container.uuid})
                for c in containers:
                    c.remove(force=True)
            else:
                containers = client.containers.list(filters={'label': str(user_id) + '-' + container.uuid})
                for c in containers:
                    c.remove(force=True)

                for n in networks:
                    for ac in auto_containers:
                        n.disconnect(ac)
                    n.remove()


        except:
            if not is_retry:
                DockerUtils.remove_current_docker_container(user_id, True)
