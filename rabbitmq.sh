#!/bin/sh

rabbitmqctl add_user lookit-admin admin
rabbitmqctl set_user_tags lookit-admin administrator
rabbitmqctl set_permissions -p / lookit-admin '.*' '.*' '.*'
rabbitmq-plugins enable rabbitmq_management
rabbitmqadmin declare queue  --vhost=/ name=email
rabbitmqadmin declare queue  --vhost=/ name=builds
rabbitmqadmin declare queue  --vhost=/ name=cleanup
