#!/usr/bin/env python
from __future__ import print_function
import re
import subprocess
import argparse
from distutils.version import LooseVersion
import requests
from datetime import datetime
import json
import sys

DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

# taken from http://stackoverflow.com/questions/25470844/specify-format-for-input-arguments-argparse-python#answer-25470943
def valid_date(date_str):
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(date_str)
        raise argparse.ArgumentTypeError(msg)

def get_created_date_for_tag(tag, repository, auth, args):
    response = requests.get(args.registry_url + "/v2/" + repository + "/manifests/" + tag,
                            auth=auth, verify=args.no_check_certificate)
    if response.json()['schemaVersion'] == 1:
        created_str = json.loads(response.json()['history'][0]['v1Compatibility'])['created'].split(".")[0]
    elif response.json()['schemaVersion'] == 2:
        digest = response.json()["config"]["digest"]
        response = requests.get(args.registry_url + "/v2/" + repository + "/blobs/" + digest,
                                auth=auth, verify=args.no_check_certificate)
        created_str = response.json()['created'].split(".")[0]
    return(datetime.strptime(created_str,"%Y-%m-%dT%H:%M:%S"))

def main():
    """cli entrypoint"""
    parser = argparse.ArgumentParser(description="Cleanup docker registry")
    parser.add_argument("-e", "--exclude",
                        dest="exclude",
                        help="Regexp to exclude tags")
    parser.add_argument("-E", "--include",
                        dest="include",
                        help="Regexp to include tags")
    parser.add_argument("-i", "--image",
                        dest="image",
                        required=True,
                        help="Docker image to cleanup")
    parser.add_argument("-v", "--verbose",
                        dest="verbose",
                        action="store_true",
                        help="verbose")
    parser.add_argument("-u", "--registry-url",
                        dest="registry_url",
                        default="http://localhost",
                        help="Registry URL")
    parser.add_argument("-s", "--script-path",
                        dest="script_path",
                        default="/usr/local/bin/delete_docker_registry_image",
                        help="delete_docker_registry_image full script path")
    parser.add_argument("-l", "--last",
                        dest="last",
                        type=int,
                        help="Keep last N tags")
    parser.add_argument("-b", "--before-date",
                        dest="before",
                        type=valid_date,
                        help="Only delete tags created before given date. " +
                             "The date must be given in the format " +
                             "'YYYY-MM-DDTHH24:mm:ss' (e.q. '" +
                             datetime.now().strftime(DATE_FORMAT) + "').")
    parser.add_argument("-a", "--after-date",
                        dest="after",
                        type=valid_date,
                        help="Only delete tags created after given date. " +
                             "The date must be given in the format " +
                             "'YYYY-MM-DDTHH24:mm:ss' (e.q. '" +
                             datetime.now().strftime(DATE_FORMAT) + "').")
    parser.add_argument("-o", "--order",
                        dest="order",
                        choices=['name', 'date'],
                        default='name',
                        help="Selects the order in which tags are sorted when the option '--last' is used")
    parser.add_argument("-U", "--user",
                        dest="user",
                        help="User for auth")
    parser.add_argument("-P", "--password",
                        dest="password",
                        help="Password for auth")
    parser.add_argument("--no_check_certificate",
			action='store_false')
    args = parser.parse_args()

    # Get catalog
    if args.user and args.password:
        auth = (args.user, args.password)
    else:
        auth = None
    response = requests.get(args.registry_url + "/v2/_catalog",
                            auth=auth, verify=args.no_check_certificate)
    repositories = response.json()["repositories"]
    # For each repository check it matches with args.image
    for repository in repositories:
        if re.search(args.image, repository):
            # Get tags
            response = requests.get(args.registry_url + "/v2/" + repository + "/tags/list",
                                    auth=auth, verify=args.no_check_certificate)
            tags = response.json()["tags"]

            # For each tag, check it does not matches with args.exclude
            matching_tags = []
            for tag in tags:
                if not args.exclude or not re.search(args.exclude, tag):
                    if not args.include or re.search(args.include, tag):
                        matching_tags.append(tag)

            # Sort tags
            if args.order == 'name':
                order_fn = lambda s: LooseVersion(re.sub('[^0-9.]', '9', s))
            else:
                order_fn = lambda s: get_created_date_for_tag(tag, repository, auth, args)

            matching_tags.sort(key=order_fn)

            # Set number of last tags to keep to the default value of 5
            # if none of the arguments 'before', 'after' and 'last' is defined
            if not args.before and not args.after and not args.last:
                args.last = 5

            # Delete all except N last items
            if args.last is not None and args.last > 0:
                matching_tags = matching_tags[:-args.last]
            else:
                matching_tags = matching_tags

            tags_to_delete = []
            if args.before or args.after:
                for tag in matching_tags:
                    created = get_created_date_for_tag(tag, repository, auth, args)

                    if (not args.before or created < args.before) and (not args.after or created > args.after) :
                        tags_to_delete.append(tag)
            else:
                tags_to_delete = matching_tags

            for tag in tags_to_delete:
                command2run = "{0} --image {1}:{2}". \
                    format(args.script_path, repository, tag)
                print("Running: {0}".format(command2run))
                out = subprocess.Popen(command2run, shell=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT).stdout.read()
                print(out)


if __name__ == '__main__':
    main()
