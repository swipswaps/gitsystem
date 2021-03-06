#!/usr/bin/env python

'''
Script that receives repo-related messages through Kafka.
'''

import argparse
import json
from json import loads
import subprocess
import os
import sys


SUPPORTED_COMMANDS = [
    'NEW',
    'DELETE',
    'UPDATE',
    'CHANGE_SERVER',
    'UPDATE_PWDS']


def parse_args():
    """Parse command-line"""
    parser = argparse.ArgumentParser()
    parser.add_argument('message', help='Serialized command message')
    return parser.parse_args()


def interpret_as_new(args):
    def make_full_git_url(
        src, repo_name): return src + '/' + repo_name
    command = {
        'type': args['type'],
        'src': make_full_git_url(args['src'], args['repo_name']),
        'repo_name': args['repo_name']
    }

    subprocess.check_call(
        "/var/www/git_tools/repo_tools/mirror_repo.sh %s %s" %
        (str(
            command['src']), str(
            command['repo_name'])), shell=True)

    return command


def interpret_as_delete(args):
    command = {
        'type': args['type'],
        'repo_name': args['repo_name']
    }

    subprocess.check_call(
        "rm -rf /var/www/html/git/%s" %
        (str(command['repo_name'])), shell=True)

    return command


def interpret_as_update(args):
    command = {
        'type': args['type'],
        'repo_name': args['repo_name']
    }

    subprocess.check_call(
        "/var/www/git_tools/repo_tools/update_mirror.sh %s" %
        (str(
            command['repo_name'])),
        shell=True)
    return command


def is_ipv4(s):
    try:
        parts = [int(e) for e in s.strip().split('.')]
        return len(parts) == 4
    except Exception:
        return False


def interpret_as_change_server(args):
    # TODO: verify logic if is_my_ip(args['src']):
    #       1. remove origin from all repositories (become main server)
    #       2. stop receive.py (sys.exit(0))
    def get_ipv4(ip_str):
        ip_str = ip_str.strip()
        for ip in ip_str.split(' '):
            if is_ipv4(ip):
                return ip

    def is_my_ip(ip):
        hostname_info = subprocess.check_output(['hostname', '-I'])
        my_ip = get_ipv4(hostname_info.strip())
        if ip.strip().strip('git://').strip('/') == my_ip:
            return True
        return False

    i_am_new_main_server = is_my_ip(args['src'])

    command = {
        'type': args['type'],
        'src': args['src']
    }

    for repo in [e for e in os.listdir(
            '/var/www/html/git/') if e.endswith('.git')]:
        if i_am_new_main_server:
            # remove origin
            subprocess.check_call(
                "/var/www/git_tools/repo_tools/remove_remote_origin.sh %s" % (str(repo)), shell=True)
            # add hooks
            subprocess.check_call(
                "/var/www/git_tools/repo_tools/add_hooks.sh %s" %(str(repo)), shell=True)
        else:
            # update origin to new url
            subprocess.check_call(
                "/var/www/git_tools/repo_tools/update_remote_origin.sh %s %s" % (
                    str(repo), str(command['src'] + '/' + str(repo))),
                shell=True)

    if i_am_new_main_server:
        sys.exit(0)

    return command


def interpret_as_update_pwds(args):
    command = {
        'type': args['type'],
        'content': args['content'],
    }

    # update .htpasswd line by line:
    with open('/var/www/html/git/.htpasswd', 'w') as pwd_file:
        for line in command['content'].split('\\n'):
            line = line.strip()
            if not line:
                continue
            pwd_file.write(line)
            pwd_file.write('\n')

    return command


def deserialize_command(args):
    d = json.loads(args)
    command_type = d['type']
    if command_type not in SUPPORTED_COMMANDS:
        raise Exception('invalid command ' + d.command +
                        '. expected one of ' + str(SUPPORTED_COMMANDS))

    if command_type == 'NEW':
        return interpret_as_new(d)
    if command_type == 'DELETE':
        return interpret_as_delete(d)
    if command_type == 'UPDATE':
        return interpret_as_update(d)
    if command_type == 'CHANGE_SERVER':
        return interpret_as_change_server(d)
    if command_type == 'UPDATE_PWDS':
        return interpret_as_update_pwds(d)

    return None


def main():
    from kafka import KafkaConsumer
    # Change the ip to your kafka server ip adress
    # Change MAIN_NODE to the topic you created on kafka server
    consumer = KafkaConsumer(
        'MAIN_NODE',
        bootstrap_servers=['10.0.2.6:9092'],
        auto_offset_reset='latest',
        enable_auto_commit=True,
        group_id='my-group',
        value_deserializer=lambda x: loads(x.decode('utf-8')))

    for message in consumer:
        try:
            cMsg = message.value
            deserialized = deserialize_command(cMsg['msg'])
            print('Deserialized command message: ' +
                  str(deserialized))
        except Exception as e:
            print('Error happened:')
            print(str(e))


if __name__ == '__main__':
    main()
