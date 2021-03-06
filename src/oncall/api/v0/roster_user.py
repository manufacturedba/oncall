# Copyright (c) LinkedIn Corporation. All rights reserved. Licensed under the BSD-2 Clause license.
# See LICENSE in the project root for license information.

from urllib import unquote
from falcon import HTTPNotFound, HTTPBadRequest

from ...auth import login_required, check_team_auth
from ...utils import load_json_body, unsubscribe_notifications, create_audit
from ... import db
from ...constants import ROSTER_USER_DELETED, ROSTER_USER_EDITED


@login_required
def on_delete(req, resp, team, roster, user):
    """
    Delete user from a roster for a team
    """
    team, roster = unquote(team), unquote(roster)
    check_team_auth(team, req)
    connection = db.connect()
    cursor = connection.cursor()

    cursor.execute('''DELETE FROM `roster_user`
                      WHERE `roster_id`=(
                          SELECT `roster`.`id` FROM `roster`
                          JOIN `team` ON `team`.`id`=`roster`.`team_id`
                          WHERE `team`.`name`=%s AND `roster`.`name`=%s)
                      AND `user_id`=(SELECT `id` FROM `user` WHERE `name`=%s)''',
                   (team, roster, user))
    deleted = cursor.rowcount
    if deleted == 0:
        raise HTTPNotFound()
    create_audit({'roster': roster, 'user': user}, team, ROSTER_USER_DELETED, req, cursor)

    # Remove user from the team if needed
    query = '''DELETE FROM `team_user` WHERE `user_id` = (SELECT `id` FROM `user` WHERE `name`=%s) AND `user_id` NOT IN
                   (SELECT `roster_user`.`user_id`
                    FROM `roster_user` JOIN `roster` ON `roster`.`id` = `roster_user`.`roster_id`
                    WHERE team_id = (SELECT `id` FROM `team` WHERE `name`=%s)
                   UNION
                   (SELECT `user_id` FROM `team_admin`
                    WHERE `team_id` = (SELECT `id` FROM `team` WHERE `name`=%s)))
               AND `team_user`.`team_id` = (SELECT `id` FROM `team` WHERE `name` = %s)'''
    cursor.execute(query, (user, team, team, team))
    if cursor.rowcount != 0:
        unsubscribe_notifications(team, user, cursor)
    connection.commit()
    cursor.close()
    connection.close()


@login_required
def on_put(req, resp, team, roster, user):
    """
    Put a user into/out of rotation
    """
    team, roster = unquote(team), unquote(roster)
    check_team_auth(team, req)
    data = load_json_body(req)

    in_rotation = data.get('in_rotation')
    if in_rotation is None:
        raise HTTPBadRequest('incomplete data', 'missing field "in_rotation"')
    in_rotation = int(in_rotation)
    connection = db.connect()
    cursor = connection.cursor()

    cursor.execute('UPDATE `roster_user` SET `in_rotation`=%s '
                   'WHERE `user_id` = (SELECT `id` FROM `user` WHERE `name`=%s)', (in_rotation, user))
    create_audit({'user': user, 'roster': roster, 'request_body': data}, team, ROSTER_USER_EDITED, req, cursor)
    connection.commit()
    cursor.close()
    connection.close()
