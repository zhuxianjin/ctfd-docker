from __future__ import division  # Use floating point for math calculations

import json
import random
import uuid
from datetime import datetime

from flask import Blueprint, render_template, request
from flask_apscheduler import APScheduler

from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES
from CTFd.utils import user as current_user
from CTFd.utils.decorators import admins_only, authed_only
from .control_utils import ControlUtil
from .db_utils import DBUtils
from .models import DynamicDockerChallenge, DynamicValueDockerChallenge


def load(app):
    # upgrade()
    app.db.create_all()
    CHALLENGE_CLASSES["dynamic_docker"] = DynamicValueDockerChallenge
    register_plugin_assets_directory(
        app, base_path="/plugins/ctfd-docker/assets/"
    )

    page_admin_blueprint = Blueprint(
        "ctfd-docker-admin-page",
        __name__,
        template_folder="templates",
        static_folder="assets",
        url_prefix="/admin/plugins/ctfd-docker"
    )

    @page_admin_blueprint.route('/settings', methods=['GET'])
    @admins_only
    def admin_list_configs():
        configs = DBUtils.get_all_configs()
        return render_template('config.html', configs=configs)

    @page_admin_blueprint.route('/settings', methods=['PATCH'])
    @admins_only
    def admin_save_configs():
        req = request.get_json()
        DBUtils.save_all_configs(req.items())
        return json.dumps({'success': True})

    @page_admin_blueprint.route("/containers", methods=['GET'])
    @admins_only
    def admin_list_containers():
        configs = DBUtils.get_all_configs()
        page = abs(request.args.get("page", 1, type=int))
        results_per_page = 50
        page_start = results_per_page * (page - 1)
        page_end = results_per_page * (page - 1) + results_per_page

        count = DBUtils.get_all_alive_container_count()
        containers = DBUtils.get_all_alive_container_page(page_start, page_end)

        pages = int(count / results_per_page) + (count % results_per_page > 0)
        return render_template("containers.html", containers=containers, pages=pages, curr_page=page,
                               curr_page_start=page_start, configs=configs)

    @page_admin_blueprint.route("/containers", methods=['DELETE'])
    @admins_only
    def admin_delete_container():
        user_id = request.args.get('user_id')
        ControlUtil.remove_container(user_id)
        return json.dumps({'success': True})

    @page_admin_blueprint.route("/containers", methods=['PATCH'])
    @admins_only
    def admin_renew_container():
        user_id = request.args.get('user_id')
        challenge_id = request.args.get('challenge_id')
        DBUtils.renew_current_container(user_id=user_id, challenge_id=challenge_id)
        return json.dumps({'success': True})

    app.register_blueprint(page_admin_blueprint)

    page_blueprint = Blueprint(
        "ctfd-docker-page",
        __name__,
        template_folder="templates",
        static_folder="assets",
        url_prefix="/plugins/ctfd-docker"
    )

    @page_blueprint.route('/container', methods=['POST'])
    @authed_only
    def add_container():
        if ControlUtil.frequency_limit():
            return json.dumps({'success': False, 'msg': 'Frequency limit, You should wait at least 1 min.'})

        user_id = current_user.get_current_user().id
        ControlUtil.remove_container(user_id)
        challenge_id = request.args.get('challenge_id')
        ControlUtil.check_challenge(challenge_id)

        configs = DBUtils.get_all_configs()
        current_count = DBUtils.get_all_alive_container_count()
        if int(configs.get("docker_max_container_count")) <= int(current_count):
            return json.dumps({'success': False, 'msg': 'Max container count exceed.'})

        dynamic_docker_challenge = DynamicDockerChallenge.query \
            .filter(DynamicDockerChallenge.id == challenge_id) \
            .first_or_404()
        flag = "flag{" + str(uuid.uuid4()) + "}"
        host = configs.get("docker_client_ip")
        while True:
            port = random.randint(10000,50000)
            if ControlUtil.is_container_port_invalid(str(host),int(port)):
                break
        if ControlUtil.add_container(user_id=user_id, challenge_id=challenge_id, flag=flag, port=port):
            return json.dumps({'success': True})
        else:
            return json.dumps({'success': False, 'msg': 'ERROR: container start failed'})

    @page_blueprint.route('/container', methods=['GET'])
    @authed_only
    def list_container():
        user_id = current_user.get_current_user().id
        challenge_id = request.args.get('challenge_id')
        ControlUtil.check_challenge(challenge_id)
        data = DBUtils.get_current_containers(user_id=user_id)
        configs = DBUtils.get_all_configs()
        if data is not None:
            if int(data.challenge_id) != int(challenge_id):
                return json.dumps({})
            return json.dumps({'success': True, 'type': 'redirect', 'ip': configs.get('docker_client_ip'),
                                   'port': data.port,
                                   'remaining_time': 3600 - (datetime.now() - data.start_time).seconds})
        else:
            return json.dumps({'success': True})

    @page_blueprint.route('/container', methods=['DELETE'])
    @authed_only
    def remove_container():
        if ControlUtil.frequency_limit():
            return json.dumps({'success': False, 'msg': 'Frequency limit, You should wait at least 1 min.'})

        user_id = current_user.get_current_user().id
        ControlUtil.remove_container(user_id)
        return json.dumps({'success': True})

    @page_blueprint.route('/container', methods=['PATCH'])
    @authed_only
    def renew_container():
        if ControlUtil.frequency_limit():
            return json.dumps({'success': False, 'msg': 'Frequency limit, You should wait at least 1 min.'})

        configs = DBUtils.get_all_configs()
        user_id = current_user.get_current_user().id
        challenge_id = request.args.get('challenge_id')
        ControlUtil.check_challenge(challenge_id)
        docker_max_renew_count = int(configs.get("docker_max_renew_count"))
        container = DBUtils.get_current_containers(user_id)
        if container.renew_count >= docker_max_renew_count:
            return json.dumps({'success': False, 'msg': 'Max renewal times exceed.'})
        DBUtils.renew_current_container(user_id=user_id, challenge_id=challenge_id)
        return json.dumps({'success': True})

    def auto_clean_container():
        with app.app_context():
            results = DBUtils.get_all_expired_container()
            for r in results:
                ControlUtil.remove_container(r.user_id)

    app.register_blueprint(page_blueprint)

    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.start()
    scheduler.add_job(id='whale-auto-clean', func=auto_clean_container, trigger="interval", seconds=10)
