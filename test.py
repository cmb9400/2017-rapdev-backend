"""Unit tests."""

import os
import database
import unittest
import tempfile
import json
import datetime

import main
from models import *


class TestCase(unittest.TestCase):
    """Unit tests for APIs."""

    def setUp(self):
        """Set up for the tests."""
        self.db_fd, self.db_name = tempfile.mkstemp()
        database.set_engine('sqlite:///' + self.db_name)
        database.init_db()
        self.app = main.app.test_client()

    def tearDown(self):
        """Cleanup from the tests."""
        database.get_db().close()
        os.close(self.db_fd)
        os.unlink(self.db_name)

    def test_auth(self):
        """Test the authentication process."""
        num_users_start = len(User.query.all())
        u = User(name="anthony", email="foo@bar.com")
        database.get_db().add(u)
        database.get_db().commit()
        assert u.id is not None
        rv = self.app.post(
            '/v1/auth',
            data='{"username":"anthony"}',
            content_type='application/json'
        )
        self.assertEquals(rv.status_code, 200)
        got = json.loads(rv.data)
        self.assertTrue('token' in got)
        self.assertTrue(len(got['token']) > 0)
        num_users = len(User.query.all())
        self.assertEquals(num_users - num_users_start, 1)

    def test_auth_makes_user(self):
        """Test that auth will create a new user."""
        num_users_start = len(User.query.all())
        rv = self.app.post(
            '/v1/auth',
            data='{"username":"bob"}',
            content_type='application/json'
        )
        self.assertEquals(rv.status_code, 200)
        got = json.loads(rv.data)
        self.assertTrue('token' in got)
        self.assertTrue(len(got['token']) > 0)
        num_users = len(User.query.all())
        self.assertEquals(num_users - num_users_start, 1)

    def test_user_not_found(self):
        """Test that get user returns a 404 for unknown users."""
        self.assertIsNone(User.query.get(100))
        rv = self.app.get(
            '/v1/user/100',
            content_type='application/json'
        )
        self.assertEquals(rv.status_code, 404)

    def test_user_found(self):
        """Test that the user is returned."""
        u = User(name='Catherine', email='cat@example.com')
        database.get_db().add(u)
        database.get_db().commit()
        rv = self.app.get(
            '/v1/user/' + str(u.id),
            content_type='application/json'
        )
        self.assertEquals(rv.status_code, 200)
        got = json.loads(rv.data)
        self.assertEquals(got["id"], u.id)
        self.assertEquals(got["name"], u.name)
        self.assertEquals(got["email"], u.email)
        self.assertEquals(len(got["teams"]), 0)
        self.assertEquals(len(got["permissions"]), 0)
        # TODO add test for presence of teams and permissions

    def test_add_team(self):
        """Test that teams can be added."""
        team_count_original = len(Team.query.all())
        u = User.query.filter_by(name='student').first()
        rv = self.app.post(
            '/v1/team',
            data='{"name": "newteam1", "type": "other_team"}',
            content_type='application/json',
            headers={"Authorization": "Bearer " + u.generate_auth_token()}
        )
        self.assertEquals(rv.status_code, 201)
        t = Team.query.filter_by(name='newteam1').first()
        self.assertEquals(t.name, 'newteam1')
        team_count = len(Team.query.all())
        self.assertEquals(team_count - team_count_original, 1)

    def test_add_team_no_permission(self):
        team_count_original = len(Team.query.all())
        u = User.query.filter_by(name='student').first()
        rv = self.app.post(
            '/v1/team',
            data='{"name": "newteam1", "type": "class"}',
            content_type='application/json',
            headers={"Authorization": "Bearer " + u.generate_auth_token()}
        )
        self.assertEquals(rv.status_code, 403)
        team_count = len(Team.query.all())
        self.assertEquals(team_count, team_count_original)

    def test_get_team_user_is_on(self):
        """Test that a user can query their own team."""
        u = User.query.filter_by(name='student').first()
        team_type = TeamType.query.filter_by(name='single').first()
        team = Team(name="testteam1")
        team.members.append(u)
        team.team_type = team_type
        database.get_db().add(team)
        database.get_db().commit()
        rv = self.app.get(
            '/v1/team/' + str(team.id),
            content_type='application/json',
            headers={"Authorization": "Bearer " + u.generate_auth_token()}
        )
        self.assertEquals(rv.status_code, 200)
        got = json.loads(rv.data)
        self.assertEquals(got["id"], team.id)
        self.assertEquals(got["name"], team.name)
        self.assertEquals(got["type"], team.team_type.name)
        self.assertEquals(len(got["members"]), 1)
        self.assertEquals(got["members"][0]["id"], u.id)
        self.assertEquals(got["members"][0]["name"], u.name)
        self.assertEquals(got["advance_time"], team.team_type.advance_time)

    def test_get_team_user_is_not_on(self):
        """Test that a non-elevated user can not query extended details of
        other teams."""
        student = User.query.filter_by(name='student').first()
        professor = User.query.filter_by(name='professor').first()
        team_type = TeamType.query.filter_by(name='single').first()
        team = Team(name="testteam1")
        team.team_type = team_type
        team.members.append(professor)
        database.get_db().add(team)
        database.get_db().commit()
        rv = self.app.get(
            '/v1/team/' + str(team.id),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + student.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 200)
        got = json.loads(rv.data)
        self.assertEquals(got["id"], team.id)
        self.assertEquals(got["type"], team.team_type.name)
        self.assertTrue("name" not in got)
        self.assertTrue("members" not in got)
        self.assertTrue("advance_time" not in got)

    def test_student_has_permission(self):
        u = User.query.filter_by(name='student').first()
        self.assertTrue(u.has_permission('room.read'))
        self.assertFalse(u.has_permission('team.create.elevated'))

    def test_failure_of_token_verify(self):
        u = User.verify_auth_token("asdfasdfsadfsadfsadfa")
        self.assertIsNone(u)

    def test_token_verify_deleted_user(self):
        self.assertIsNone(User.query.get(100))
        u = User(name="foo")
        u.id = 100
        token = u.generate_auth_token()
        got = User.verify_auth_token(token)
        self.assertIsNone(got)

    def test_delete_team(self):
        """Test that teams can be deleted and their associated reservations will be deleted."""
        team_count_original = len(Team.query.all())
        reservation_count_original = len(Reservation.query.all())
        u = User.query.filter_by(name='student').first()
        t = Team(name="testdelete")
        t.members.append(u)
        team_type = TeamType.query.filter_by(name='other_team').first()
        t.team_type = team_type
        room = Room.query.first()
        reservation = Reservation(start=datetime.datetime.now(),
                                  end=datetime.datetime.now() + datetime.timedelta(hours=1),
                                  team=t,
                                  room=room,
                                  created_by=u
                                  )
        database.get_db().add(t)
        database.get_db().add(reservation)
        database.get_db().commit()

        rv = self.app.delete(
            '/v1/team/' + str(t.id),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + u.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 204)
        team_count_new = len(Team.query.all())
        reservation_count_new = len(Reservation.query.all())
        self.assertEquals(team_count_original, team_count_new)
        self.assertEquals(reservation_count_original, reservation_count_new)

    def test_add_basic_reservation(self):
        num_reservations_before = len(Reservation.query.all())
        student = User.query.filter_by(name='student').first()
        team_type = TeamType.query.filter_by(name='other_team').first()
        team = Team(name="testteam1")
        team.team_type = team_type
        team.members.append(student)
        database.get_db().add(team)
        database.get_db().commit()

        team_id = team.id

        room = Room.query.first()

        rv = self.app.post(
            '/v1/reservation',
            data=json.dumps({
                "team_id": team.id,
                "room_id": room.id,
                "start": datetime.datetime.now().isoformat(),
                "end": (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
            }),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + student.generate_auth_token()
            }
        )

        num_reservations_after = len(Reservation.query.all())
        self.assertEquals(rv.status_code, 201)
        self.assertEquals(len(Reservation.query.filter_by(team_id=team_id).all()), 1)
        self.assertEquals(num_reservations_after - num_reservations_before, 1)

    def test_add_reservation_conflict_override(self):
        """Create a reservation, and then override it. """
        num_reservations_before = len(Reservation.query.all())
        student = User.query.filter_by(name='student').first()
        student_auth_token = student.generate_auth_token()
        room = Room.query.first()

        team_type = TeamType.query.filter_by(name='other_team').first()
        initial_team = Team(name="other_team_1")
        initial_team.team_type = team_type
        initial_team.members.append(student)
        database.get_db().add(initial_team)

        team_type = TeamType.query.filter_by(name='senior_project').first()
        override_team = Team(name="senior_project_1")
        override_team.team_type = team_type
        override_team.members.append(student)
        database.get_db().add(override_team)

        database.get_db().commit()

        initial_team_id = initial_team.id
        override_team_id = override_team.id
        room_id = room.id

        start_time = "2017-12-25T12:30:00+05:00"  # datetime.datetime.now().isoformat()
        end_time = "2017-12-25T13:30:00+05:00"  # (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()

        # Create initial reservation
        rv = self.app.post(
            '/v1/reservation',
            data=json.dumps({
                "team_id": initial_team_id,
                "room_id": room_id,
                "start": start_time,
                "end": end_time
            }),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + student_auth_token
            }
        )
        self.assertEquals(rv.status_code, 201)
        self.assertEquals(len(Reservation.query.filter_by(team_id=initial_team_id).all()), 1)

        # Attempt to create conflicting reservation
        rv = self.app.post(
            '/v1/reservation',
            data=json.dumps({
                "team_id": override_team_id,
                "room_id": room_id,
                "start": start_time,
                "end": end_time
            }),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + student_auth_token
            }
        )
        # Reservation not yet created
        self.assertEquals(rv.status_code, 409)
        response_json = json.loads(rv.data)
        self.assertTrue("overridable" in response_json)
        self.assertTrue(response_json["overridable"])
        self.assertEquals(len(Reservation.query.filter_by(team_id=override_team_id).all()), 0)

        # Actually add the new reservation, deleting the conflicting one
        rv = self.app.post(
            '/v1/reservation',
            data=json.dumps({
                "team_id": override_team_id,
                "room_id": room_id,
                "start": start_time,
                "end": end_time,
                "override": True
            }),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + student_auth_token
            }
        )
        self.assertEquals(rv.status_code, 201)

        # New reservation is created
        self.assertEquals(len(Reservation.query.filter_by(team_id=override_team_id).all()), 1)

        # Old reservation is deleted
        self.assertEquals(len(Reservation.query.filter_by(team_id=initial_team_id).all()), 0)

        num_reservations_after = len(Reservation.query.all())
        self.assertEquals(num_reservations_after - num_reservations_before, 1)

    def test_update_basic_reservation(self):
        student = User.query.filter_by(name='student').first()
        team_type = TeamType.query.filter_by(name='other_team').first()
        team = Team(name="testteam1")
        team.team_type = team_type
        team.members.append(student)
        database.get_db().add(team)

        room = Room.query.first()
        start_time = datetime.datetime.now()
        end_time = datetime.datetime.now() + datetime.timedelta(hours=1)

        token = student.generate_auth_token()

        reservation = Reservation(start=start_time,
                                  end=end_time,
                                  team=team,
                                  room=room,
                                  created_by=student
                                  )
        database.get_db().add(reservation)
        database.get_db().commit()

        reservation_id = reservation.id
        team_id = team.id

        num_reservations_before = len(Reservation.query.all())

        rv = self.app.put(
            '/v1/reservation/' + str(reservation_id),
            data=json.dumps({
                "room_id": room.id,
                "start": (start_time + datetime.timedelta(minutes=10)).isoformat(),
                "end": (end_time + datetime.timedelta(minutes=10)).isoformat()
            }),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + token
            }
        )

        num_reservations_after = len(Reservation.query.all())
        self.assertEquals(rv.status_code, 204)
        self.assertEquals(len(Reservation.query.filter_by(team_id=team_id).all()), 1)
        self.assertEquals(num_reservations_after, num_reservations_before)

    def test_update_reservation_conflict_override(self):
        """Update a reservation, and then override it. """
        student = User.query.filter_by(name='student').first()

        # Low-priority team
        team_type = TeamType.query.filter_by(name='other_team').first()
        initial_team = Team(name="other_team_1")
        initial_team.team_type = team_type
        initial_team.members.append(student)
        database.get_db().add(initial_team)

        # High-priority team
        team_type = TeamType.query.filter_by(name='senior_project').first()
        override_team = Team(name="senior_project_1")
        override_team.team_type = team_type
        override_team.members.append(student)
        database.get_db().add(override_team)

        room = Room.query.first()

        start_time = datetime.datetime.now()
        end_time = start_time + datetime.timedelta(hours=1)

        token = student.generate_auth_token()

        # Create low-priority reservation
        reservation_low = Reservation(
            start=start_time,
            end=end_time,
            team=initial_team,
            room=room,
            created_by=student
        )
        database.get_db().add(reservation_low)

        # Create high-priority reservation, right next to low-priority one
        reservation_high = Reservation(
            start=end_time,
            end=end_time + datetime.timedelta(hours=1),
            team=override_team,
            room=room,
            created_by=student
        )
        database.get_db().add(reservation_high)
        database.get_db().commit()

        reservation_high_id = reservation_high.id
        initial_team_id = initial_team.id
        override_team_id = override_team.id
        room_id = room.id

        # Attempt to update high-priority to conflict
        rv = self.app.put(
            '/v1/reservation/' + str(reservation_high_id),
            data=json.dumps({
                "room_id": room_id,
                "start": start_time.isoformat(),
                "end": (end_time + datetime.timedelta(hours=1)).isoformat()
            }),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + token
            }
        )
        # Reservation not yet updated
        self.assertEquals(rv.status_code, 409)
        response_json = json.loads(rv.data)
        self.assertTrue("overridable" in response_json)
        self.assertTrue(response_json["overridable"])
        self.assertEquals(len(Reservation.query.filter_by(team_id=override_team_id).all()), 1)
        self.assertEquals(len(Reservation.query.filter_by(team_id=initial_team_id).all()), 1)

        # Actually update the high-priority reservation, deleting the conflicting one
        rv = self.app.put(
            '/v1/reservation/' + str(reservation_high_id),
            data=json.dumps({
                "room_id": room_id,
                "start": start_time.isoformat(),
                "end": (end_time + datetime.timedelta(hours=1)).isoformat(),
                "override": True
            }),
            content_type='application/json',
            headers={
                "Authorization": "Bearer " + token
            }
        )

        self.assertEquals(rv.status_code, 204)

        self.assertEquals(len(Reservation.query.filter_by(team_id=override_team_id).all()), 1)
        self.assertEquals(len(Reservation.query.filter_by(team_id=initial_team_id).all()), 0)

    def test_delete_reservation(self):
        """Test deleting a reservation."""
        num_reservations_before = len(Reservation.query.all())
        student = User.query.filter_by(name='student').first()
        team_type = TeamType.query.filter_by(name='other_team').first()
        team = Team(name="testteam1")
        team.team_type = team_type
        team.members.append(student)
        database.get_db().add(team)

        room = Room.query.first()
        start_time = datetime.datetime.now()
        end_time = datetime.datetime.now() + datetime.timedelta(hours=1)

        token = student.generate_auth_token()

        reservation = Reservation(
            start=start_time,
            end=end_time,
            team=team,
            room=room,
            created_by=student
        )
        database.get_db().add(reservation)
        database.get_db().commit()

        reservation_id = reservation.id
        team_id = team.id

        num_reservations_after = len(Reservation.query.all())
        self.assertEquals(num_reservations_after - num_reservations_before, 1)
        self.assertEquals(len(Reservation.query.filter_by(team_id=team_id).all()), 1)

        rv = self.app.delete(
            '/v1/reservation/' + str(reservation_id),
            headers={
                "Authorization": "Bearer " + token
            }
        )

        self.assertEquals(rv.status_code, 204)
        num_reservations_after = len(Reservation.query.all())
        self.assertEquals(num_reservations_after, num_reservations_before)
        self.assertEquals(len(Reservation.query.filter_by(team_id=team_id).all()), 0)

    def test_add_team_member_valid(self):
        """Test that users can be added from teams."""
        team_creator = User.query.filter_by(name='student').first()
        t = Team(name='test')
        t.members.append(team_creator)
        team_type = TeamType.query.filter_by(name='other_team').first()
        t.team_type = team_type
        second_user = User.query.filter_by(name='labbie').first()

        database.get_db().add(t)
        database.get_db().commit()

        team_id = t.id
        second_user_id = second_user.id

        # test adding the user to the team
        rv = self.app.post(
            '/v1/team/' + str(team_id) + '/user/' + str(second_user_id),
            content_type='application/json',
            headers={
                'Authorization': 'Bearer ' + team_creator.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 201)

        new_team = Team.query.filter_by(name='test').first()
        self.assertEquals(len(new_team.members), 2)

    def test_remove_team_member_valid(self):
            """Test that users can be deleted from teams."""
            team_creator = User.query.filter_by(name='student').first()
            t = Team(name='test')
            t.members.append(team_creator)
            team_type = TeamType.query.filter_by(name='other_team').first()
            t.team_type = team_type
            second_user = User.query.filter_by(name='labbie').first()
            t.members.append(second_user)

            database.get_db().add(t)
            database.get_db().commit()

            team_id = t.id
            second_user_id = second_user.id

            # test removing the user from the team
            rv = self.app.delete(
                '/v1/team/' + str(team_id) + '/user/' + str(second_user_id),
                content_type='application/json',
                headers={
                    'Authorization': 'Bearer ' + team_creator.generate_auth_token()
                }
            )
            self.assertEquals(rv.status_code, 204)

            new_team = Team.query.filter_by(name='test').first()
            self.assertEquals(len(new_team.members), 1)

    def test_reservation_read(self):
        u = User.query.filter_by(name='student').first()
        t = Team(name="testdelete")
        t.members.append(u)
        team_type = TeamType.query.filter_by(name='single').first()
        t.team_type = team_type
        room = Room.query.first()
        reservation = Reservation(start=datetime.datetime.now(),
                                  end=datetime.datetime.now() + datetime.timedelta(hours=1),
                                  team=t,
                                  room=room,
                                  created_by=u
                                  )
        database.get_db().add(t)
        database.get_db().add(reservation)
        database.get_db().commit()
        # test removing the user from the team
        rv = self.app.get(
            '/v1/reservation/' + str(reservation.id),
            content_type='application/json',
            headers={
                'Authorization': 'Bearer ' + u.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 200)
        got = json.loads(rv.data)
        self.assertEquals(got["team"]["name"], t.name)
        self.assertEquals(got["start"], reservation.start.isoformat())
        self.assertEquals(got["end"], reservation.end.isoformat())
        self.assertEquals(got["room"]["number"], reservation.room.number)
        self.assertEquals(got["id"], reservation.id)

    def test_room_read(self):
        """ test that querying an existing room returns json data """
        room = Room.query.first()

        rv = self.app.get(
            '/v1/room/' + str(room.id),
            content_type='application/json',
        )
        got = json.loads(rv.data)
        self.assertTrue('features' in got)
        self.assertTrue(len(got['features']) > 0)

    def test_room_not_found(self):
        """Test that get room returns a 404 for unknown rooms."""
        self.assertIsNone(Room.query.get(100))
        rv = self.app.get(
            '/v1/room/100',
            content_type='application/json'
        )
        self.assertEquals(rv.status_code, 404)

    def test_add_team_member_invalid_not_on_team(self):
        """Test that users can be added from teams."""
        team_creator = User.query.filter_by(name='student').first()
        t = Team(name='test')
        t.members.append(team_creator)
        team_type = TeamType.query.filter_by(name='other_team').first()
        t.team_type = team_type
        second_user = User.query.filter_by(name='labbie').first()

        database.get_db().add(t)
        database.get_db().commit()

        team_id = t.id
        second_user_id = second_user.id

        # test adding the user to the team
        rv = self.app.post(
            '/v1/team/' + str(team_id) + '/user/' + str(second_user_id),
            content_type='application/json',
            headers={
                'Authorization': 'Bearer ' + second_user.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 403)

        new_team = Team.query.filter_by(name='test').first()
        self.assertEquals(len(new_team.members), 1)

    def test_add_team_member_invalid_single_team(self):
        """Test that users can be added from teams."""
        team_creator = User.query.filter_by(name='student').first()
        t = Team(name='test')
        t.members.append(team_creator)
        team_type = TeamType.query.filter_by(name='single').first()
        t.team_type = team_type
        second_user = User.query.filter_by(name='labbie').first()

        database.get_db().add(t)
        database.get_db().commit()

        team_id = t.id
        second_user_id = second_user.id

        # test adding the user to the team
        rv = self.app.post(
            '/v1/team/' + str(team_id) + '/user/' + str(second_user_id),
            content_type='application/json',
            headers={
                'Authorization': 'Bearer ' + team_creator.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 400)

        new_team = Team.query.filter_by(name='test').first()
        self.assertEquals(len(new_team.members), 1)

    def test_add_team_member_invalid_user_id(self):
        """Test that users can be added from teams."""
        team_creator = User.query.filter_by(name='student').first()
        t = Team(name='test')
        t.members.append(team_creator)
        team_type = TeamType.query.filter_by(name='other_team').first()
        t.team_type = team_type

        database.get_db().add(t)
        database.get_db().commit()

        team_id = t.id

        self.assertIsNone(User.query.get(100))

        # test adding the user to the team
        rv = self.app.post(
            '/v1/team/' + str(team_id) + '/user/' + '100',
            content_type='application/json',
            headers={
                'Authorization': 'Bearer ' + team_creator.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 400)

        new_team = Team.query.filter_by(name='test').first()
        self.assertEquals(len(new_team.members), 1)

    def test_add_team_member_invalid_already_in_team(self):
        """Test that users can be added from teams."""
        team_creator = User.query.filter_by(name='student').first()
        t = Team(name='test')
        t.members.append(team_creator)
        team_type = TeamType.query.filter_by(name='other_team').first()
        t.team_type = team_type
        second_user = User.query.filter_by(name='labbie').first()
        t.members.append(second_user)

        database.get_db().add(t)
        database.get_db().commit()

        team_id = t.id
        second_user_id = second_user.id

        # test adding the user to the team
        rv = self.app.post(
            '/v1/team/' + str(team_id) + '/user/' + str(second_user_id),
            content_type='application/json',
            headers={
                'Authorization': 'Bearer ' + team_creator.generate_auth_token()
            }
        )
        self.assertEquals(rv.status_code, 409)

        new_team = Team.query.filter_by(name='test').first()
        self.assertEquals(len(new_team.members), 2)


if __name__ == '__main__':
    unittest.main()
