import time
import socket

from CTFd.models import Challenges
from .db_utils import DBUtils
from .docker_utils import DockerUtils
from sqlalchemy.sql import and_
from flask import session


class ControlUtil:
    @staticmethod
    def add_container(user_id, challenge_id, flag, port=0):
        return DockerUtils.add_new_docker_container(user_id=user_id, challenge_id=challenge_id, flag=flag, port=port)

    @staticmethod
    def remove_container(user_id):
        DockerUtils.remove_current_docker_container(user_id)
        DBUtils.remove_current_container(user_id)

    @staticmethod
    def check_challenge(challenge_id):
        Challenges.query.filter(
            Challenges.id == challenge_id,
            and_(Challenges.state != "hidden", Challenges.state != "locked"),
        ).first_or_404()

    @staticmethod
    def frequency_limit():
        if "limit" not in session:
            session["limit"] = int(time.time())
            return False

        if int(time.time()) - session["limit"] < 60:
            return True

        session["limit"] = int(time.time())
        return False

    @staticmethod
    def is_container_port_invalid(host,port):
        s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            s.connect((host,int(port)))
            s.shutdown(2)
            return False
        except:
            return True