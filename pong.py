# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ***** END GPL LICENSE BLOCK *****
import pathlib
import random
import tempfile

import aud
import bpy
import math

AUD_DEVICE = aud.Device()
SOUND_FILES = {}
TMPDIR = tempfile.TemporaryDirectory()


class ScoreDisplay:
    def __init__(self, bl_digit_objects):
        self._modifiers = tuple(
            bl_object.modifiers['Array']
            for bl_object in bl_digit_objects
        )
        n_digits = len(self._modifiers)
        self._string_format = f"{{:0{n_digits}d}}"

    def _set_digit(self, index, value: int):
        self._modifiers[index].offset_u = value * 0.1

    def display_value(self, value):
        string = self._string_format.format(value)
        reversed_string = string[::-1]
        clamped_string = reversed_string[:len(self._modifiers)]
        for index, char in enumerate(clamped_string):
            self._set_digit(index, int(char))


class PlayArea:
    def __init__(self, size, glow_control_object):
        self.ranges = [
            self._range_from_size(size[0]),
            self._range_from_size(size[1]),
            self._range_from_size(size[2]),
        ]
        self.bound_glow_control = glow_control_object.scale
        self.glow_timer = 0
        self.glow_time = 0.15
        self._glow = False

    @staticmethod
    def _range_from_size(size_dimension):
        return -size_dimension / 2, size_dimension / 2

    @property
    def glow(self):
        return self._glow

    @glow.setter
    def glow(self, value):
        if value:
            self.bound_glow_control[0] = 1
            self.glow_timer = self.glow_time
        else:
            self.bound_glow_control[0] = 0

        self._glow = value

    def update(self, time_delta):
        if self.glow and self.glow_timer > 0:
            self.glow_timer -= time_delta
            if self.glow_timer <= 0:
                self.glow = False

    def on_hit(self):
        self.glow = True


class Ball:
    def __init__(self, blender_object, glow_control_object,
                 spawn_laser_objects, speed, spawn_jitter=(3, 3, 3)):

        self.glow_time = 1
        self.glow_timer = self.glow_time
        self._glow = False

        self.sound_hit = aud.Sound.file(SOUND_FILES['hit'])
        self.sound_spawn = aud.Sound.file(SOUND_FILES['hit2'])

        self.dimensions = blender_object.dimensions
        self.lasers = spawn_laser_objects

        self.ranges = [
            (0, 0),
            (0, 0),
            (0, 0),
        ]
        self.direction_choices = (-0.5, 0.5)

        self.spawn_jitter = spawn_jitter
        self.bound_location = blender_object.location

        self.speed = speed
        self.direction = [0, 0, 0]
        self.position = [0, 0, 0]
        self.game: 'PongGame' = None
        self.bound_glow_control = glow_control_object.scale

    def spawn(self, speed):
        self._play_sound(self.sound_spawn, 30)
        self.glow = True
        self._set_laser_visibility(True)

        self.speed = speed
        self._set_new_position(
            (
                self.spawn_jitter[0] * (random.random() - 0.5),
                20,
                self.spawn_jitter[2] * (random.random() - 0.5),
            )
        )

        self.direction[0] = random.choice(self.direction_choices)
        self.direction[1] = -1
        self.direction[2] = random.choice(self.direction_choices)
        self._apply_normalization(self.direction)
        self._apply_factor(self.direction, speed)

    def _set_laser_visibility(self, visible):
        for object in self.lasers:
            object.hide_viewport = not visible

    def _set_new_position(self, new_position):
        self.position[0] = new_position[0]
        self.position[1] = new_position[1]
        self.position[2] = new_position[2]
        self._update_visible_position()

    def _update_visible_position(self):
        self.bound_location[0] = self.position[0]
        self.bound_location[1] = self.position[1]
        self.bound_location[2] = self.position[2]

    def _apply_normalization(self, direction):
        factor = math.sqrt(
            direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2
        )
        self._apply_factor(direction, factor)

    @staticmethod
    def _apply_factor(direction, factor):
        direction[0] *= factor
        direction[1] *= factor
        direction[2] *= factor

    def apply_movement_range_from_area(self, play_area: 'PlayArea'):
        for i, (area_range, size) in enumerate(
                zip(play_area.ranges, self.dimensions)
        ):
            self.ranges[i] = (
                area_range[0] + size / 2,
                area_range[1] - size / 2,
            )

    def update(self, time_delta):
        if self.glow and self.glow_timer > 0:
            self.glow_timer -= time_delta
            self.bound_glow_control[0] = min(1, self.glow_timer)
            if self.glow_timer <= 0:
                self.glow = False

        self._apply_wall_collision(self.direction)
        self._apply_mover_collision(
            self.game.mover, self.position, self.direction)
        self._update_kinematics(time_delta)

    def _update_kinematics(self, time_delta):
        self.position[0] += self.direction[0] * time_delta
        self.position[1] += self.direction[1] * time_delta
        self.position[2] += self.direction[2] * time_delta
        self._update_visible_position()

    def _apply_wall_collision(self, direction):
        self._collide_max(direction, 0)
        self._collide_min(direction, 0)
        self._collide_max(direction, 1, call=self.game.goal_hit)
        # no min, 1 collision on purpose
        self._collide_max(direction, 2)
        self._collide_min(direction, 2)

    def _collide_max(self, direction, axis, call=None):
        if self.position[axis] > self.ranges[axis][1]:
            self.position[axis] = self.ranges[axis][1]
            self._reflect(direction, axis, self.game.play_area)
            if call is not None:
                call()

    def _collide_min(self, direction, axis):
        if self.position[axis] < self.ranges[axis][0]:
            self.position[axis] = self.ranges[axis][0]
            self._reflect(direction, axis, self.game.play_area)

    def _reflect(self, direction, index, obstacle):
        self._play_sound(self.sound_hit, 10)
        direction[index] = -direction[index]
        obstacle.on_hit()

    def _play_sound(self, sound, distance_reference):
        handle = AUD_DEVICE.play(sound)
        handle.location = tuple(self.bound_location)
        handle.distance_reference = distance_reference

    def _apply_mover_collision(
            self, mover: 'Mover', position, direction, depth_tolerance=0.2
    ):
        depth = depth_tolerance * self.speed
        if (
                mover.position[1] - depth
                < position[1]
                < mover.position[1]
        ):
            if (
                    self._is_within_cross_section_limits(position, mover, 0)
                    and
                    self._is_within_cross_section_limits(position, mover, 2)
            ):
                self.position[1] = mover.position[1]
                self._reflect(direction, 1, self.game.mover)

        elif position[1] < mover.position[1] - 42:
            self.game.mover_missed()

    def _is_within_cross_section_limits(self, position, target, axis):
        limits = (
            target.position[axis]
            - target.dimensions[axis] / 2
            - self.dimensions[axis] / 2
            ,
            target.position[axis]
            + target.dimensions[axis] / 2
            + self.dimensions[axis] / 2
        )
        return limits[0] < position[axis] < limits[1]

    @property
    def glow(self):
        return self._glow

    @glow.setter
    def glow(self, value):
        if value:
            self._set_laser_visibility(True)
            self.bound_glow_control[0] = 1
            self.glow_timer = self.glow_time
        else:
            self._set_laser_visibility(False)
            self.bound_glow_control[0] = 0

        self._glow = value


class Mover:
    CMD_UP, CMD_DOWN, CMD_LEFT, CMD_RIGHT = 0, 1, 2, 3

    def __init__(self, blender_object, glow_control_object,
                 control_laser_objects,
                 speed_directions=(1.0, 0, 1.0), speed_value=1):
        self.glow_timer = 0
        self.glow_time = 0.15
        self.x_range_base = [0, 0]
        self.z_range_base = [0, 0]
        self.ranges = [
            (0, 0),
            (0, 0),
            (0, 0),
        ]
        self._speed_directions = speed_directions
        self._speeds = speed_directions
        self._speed_value = speed_value
        self.speed = speed_value
        self.bound_location = blender_object.location
        self.bound_scale = blender_object.scale
        self.bound_glow_control = glow_control_object.scale
        self.blender_object = blender_object
        self.dimensions = blender_object.dimensions
        self.visibilty_objects = set(control_laser_objects)
        self.visibilty_objects.add(blender_object)

        self.position = [0, self.bound_location[1], 0]
        self._visible = True
        self._glow = False
        self.sound = aud.Sound.file(SOUND_FILES['hit2'])

        self.command_map = {
            self.CMD_UP: self._increase_z,
            self.CMD_DOWN: self._decrease_z,
            self.CMD_LEFT: self._decrease_x,
            self.CMD_RIGHT: self._increase_x,
        }
        self.active_commands = set()
        self.visible = True

    @property
    def speed(self):
        return self._speed_value

    @speed.setter
    def speed(self, value):
        self._speed_value = value
        self._speeds = tuple(speed * value for speed in self._speed_directions)

    def on_hit(self):
        self.resize(0.8)
        handle = AUD_DEVICE.play(self.sound)
        handle.location = tuple(self.bound_location)
        handle.distance_reference = 15
        self.glow = True

    def resize(self, factor):
        self.bound_scale[0] = factor * self.bound_scale[0]
        self.bound_scale[2] = factor * self.bound_scale[2]

    def set_size(self, value):
        self.bound_scale[0] = value
        self.bound_scale[2] = value

    def apply_movement_range_from_area(self, play_area: 'PlayArea'):
        for i, area_range in enumerate(play_area.ranges):
            self.ranges[i] = area_range
        self.resize(1)

    def start_command(self, command):
        self.active_commands.add(command)

    def stop_command(self, command):
        try:
            self.active_commands.remove(command)
        except KeyError:
            pass

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, visible):
        self._visible = visible
        for object in self.visibilty_objects:
            object.hide_viewport = not visible

    def update(self, time_delta):
        if self.glow and self.glow_timer > 0:
            self.glow_timer -= time_delta
            if self.glow_timer <= 0:
                self.glow = False

        for command in self.active_commands:
            self.command_map[command](time_delta)
            self.bound_location[0] = self.position[0]
            self.bound_location[2] = self.position[2]

    def _increase_x(self, time_delta):
        self._increase_axis(0, time_delta)

    def _decrease_x(self, time_delta):
        self._decrease_axis(0, time_delta)

    def _increase_z(self, time_delta):
        self._increase_axis(2, time_delta)

    def _decrease_z(self, time_delta):
        self._decrease_axis(2, time_delta)

    def _increase_axis(self, i, time_delta):
        self.position[i] += self._speeds[i] * time_delta

        limit = self.ranges[i][1] - self.dimensions[i] / 2
        if self.position[i] > limit:
            self.position[i] = limit

    def _decrease_axis(self, i, time_delta):
        self.position[i] -= self._speeds[i] * time_delta

        limit = self.ranges[i][0] + self.dimensions[i] / 2
        if self.position[i] < limit:
            self.position[i] = limit

    @property
    def glow(self):
        return self._glow

    @glow.setter
    def glow(self, value):
        if value:
            self.bound_glow_control[0] = 1
            self.glow_timer = self.glow_time
        else:
            self.bound_glow_control[0] = 0

        self._glow = value


class PongGame:
    INITIAL_BALL_SPEED = 8
    INITIAL_MOVER_SPEED = 10
    INITIAL_SCORE_FACTOR = 100000000

    @staticmethod
    def setup_ball(blender_object_name, glow_control_name,
                   laser_object_name_base):
        ball_obj = bpy.data.objects[blender_object_name]
        glow_control_obj = bpy.data.objects[glow_control_name]
        spawn_laser_objs = (
            bpy.data.objects[laser_object_name_base + ".left"],
            bpy.data.objects[laser_object_name_base + ".right"]
        )
        ball = Ball(ball_obj, glow_control_obj, spawn_laser_objs, 6)
        return ball

    @staticmethod
    def setup_mover(blender_object_name, laser_object_name_base,
                    glow_control_name):
        mover_obj = bpy.data.objects[blender_object_name]
        glow_control_obj = bpy.data.objects[glow_control_name]
        laser_objs = (
            bpy.data.objects[laser_object_name_base + ".left"],
            bpy.data.objects[laser_object_name_base + ".right"],
            bpy.data.objects[laser_object_name_base + ".top"]
        )
        mover = Mover(mover_obj, glow_control_obj, laser_objs)
        return mover

    @staticmethod
    def setup_play_area(blender_object_name, glow_control_name):
        area_obj = bpy.data.objects[blender_object_name]
        glow_control_obj = bpy.data.objects[glow_control_name]
        area_dimension = area_obj.dimensions
        area_size = (
            area_dimension[0],
            area_dimension[1],
            area_dimension[2],
        )
        play_area = PlayArea(area_size, glow_control_obj)
        return play_area

    @staticmethod
    def setup_score_display(name_base, number_of_digits):
        object_names = (name_base.format(i) for i in range(number_of_digits))
        objects = (
            bpy.data.objects[obj] for obj in object_names
        )
        score_display = ScoreDisplay(objects)
        return score_display

    def __init__(self, play_area: 'PlayArea', mover: 'Mover', ball: 'Ball',
                 score_display: 'ScoreDisplay', game_over_control_object):
        mover.apply_movement_range_from_area(play_area)
        ball.apply_movement_range_from_area(play_area)
        ball.game = self
        self.ball = ball
        self.ball.speed = self.INITIAL_BALL_SPEED
        self.mover = mover
        self.mover.speed = self.INITIAL_MOVER_SPEED
        self.play_area = play_area
        self.score_display = score_display
        self.bound_game_over_control = game_over_control_object.scale
        self._is_game_over = False

        self.round = 0
        self.has_mover_been_hit = False
        self.score_factor = self.INITIAL_SCORE_FACTOR
        self._score = 0

        self.command_for_key_type = {
            'LEFT_ARROW': Mover.CMD_LEFT,
            'RIGHT_ARROW': Mover.CMD_RIGHT,
            'UP_ARROW': Mover.CMD_UP,
            'DOWN_ARROW': Mover.CMD_DOWN,
        }
        self.action_for_key_state = {
            'PRESS': self.mover.start_command,
            'RELEASE': self.mover.stop_command,
        }

        self.restart_game_key = ('UP_ARROW', 'PRESS')

        self.score = 0
        self.game_over()

    def new_round(self, ball_speed_factor=1.0, mover_speed_factor=1.0):
        self.has_mover_been_hit = False
        self.round += 1
        self.score_factor //= 10
        self.ball.spawn(ball_speed_factor * self.ball.speed)
        self.mover.glow = True
        self.mover.speed *= mover_speed_factor
        self.mover.set_size(1)

    def new_game(self):
        self._is_game_over = False
        self.bound_game_over_control[0] = 0
        self.round = 0
        self.score_factor = self.INITIAL_SCORE_FACTOR
        self.ball.speed = self.INITIAL_BALL_SPEED
        self.mover.speed = self.INITIAL_MOVER_SPEED
        self.mover.visible = True
        self.score = 0
        self.new_round()

    def game_over(self):
        self._is_game_over = True
        self.mover.visible = False
        self.bound_game_over_control[0] = 1

    def update(self, time_delta):
        if not self._is_game_over:
            self.mover.update(time_delta)
            self.ball.update(time_delta)
            self.play_area.update(time_delta)

    def mover_missed(self):
        if self.has_mover_been_hit:
            self.new_round(ball_speed_factor=1.2, mover_speed_factor=1.1)
        else:
            self.game_over()

    def goal_hit(self):
        self.has_mover_been_hit = True
        self.score += self.score_factor

    @property
    def score(self):
        return self._score

    @score.setter
    def score(self, value: int):
        self._score = value
        self.score_display.display_value(value)

    def set_event(self, event):
        if self._is_game_over:
            if (event.type, event.value) == self.restart_game_key:
                self.new_game()
        elif event.type in self.command_for_key_type:
            action = self.action_for_key_state[event.value]
            action(self.command_for_key_type[event.type])


class PongHandler(bpy.types.Operator):
    bl_idname = "wm.pong_handler"
    bl_label = "Pong Handler"
    update_rate = 1 / 30
    _loading_screen_obj = bpy.data.objects['loading']
    _game_collection = bpy.data.collections['area']
    _waiting_timer = 8
    _modal_action = None
    _timer = None
    game = None

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(
            self.update_rate, window=context.window)
        wm.modal_handler_add(self)
        self._modal_action = self._update_waiting

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self._cancel(context)
            cleanup_and_quit()
            return {'CANCELLED'}

        elif event.type == 'TIMER':
            self._modal_action()

        elif self.game is not None:
            self.game.set_event(event)

        return {'RUNNING_MODAL'}

    def _cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

    def _update_waiting(self):
        self._waiting_timer -= self.update_rate
        if self._waiting_timer <= 0:
            self._initialize()
            bpy.ops.screen.animation_play()
            self._modal_action = self._update_running

    def _initialize(self):
        game = PongGame(
            play_area=PongGame.setup_play_area(
                "area", "area_glow_control"),
            mover=PongGame.setup_mover(
                "p1", 'laser', "p1_glow_control"),
            ball=PongGame.setup_ball(
                "ball", "ball_glow_control", "laser.ball"),
            score_display=PongGame.setup_score_display(
                'score.d{}', 9),
            game_over_control_object=bpy.data.objects['game_over_control']
        )

        self.game = game
        self._loading_screen_obj.hide_viewport = True
        self._game_collection.hide_viewport = False

    def _update_running(self):
        self.game.update(self.update_rate)


def cleanup_and_quit():
    AUD_DEVICE.stopAll()
    unregister()
    if TMPDIR:
        TMPDIR.cleanup()
    bpy.ops.wm.quit_blender()


def register():
    bpy.utils.register_class(PongHandler)


def unregister():
    bpy.utils.unregister_class(PongHandler)


def write_data_to(hit_file, data):
    with open(hit_file, 'wb'):
        hit_file.write_bytes(data)


def unpack_sounds_tmp():
    global SOUND_FILES
    tmp_path = pathlib.Path(TMPDIR.name)
    hit_file = tmp_path / 'hit.wav'
    hit2_file = tmp_path / 'hit2.wav'
    write_data_to(hit_file, bpy.data.sounds['hit.wav'].packed_file.data)
    write_data_to(hit2_file, bpy.data.sounds['hit2.wav'].packed_file.data)
    SOUND_FILES['hit'] = str(hit_file)
    SOUND_FILES['hit2'] = str(hit2_file)


def setup_workspace():
    window = bpy.context.window_manager.windows[0]
    screen = window.screen
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces[0]
            space.shading.type = 'RENDERED'
            override = {'window': window, 'screen': screen, 'area': area}
            bpy.ops.screen.screen_full_area(override, use_hide_panels=True)
            break


def main():
    setup_workspace()
    unpack_sounds_tmp()
    register()
    listener = bpy.data.objects['aud_listener']
    AUD_DEVICE.listener_location = tuple(listener.location)
    AUD_DEVICE.listener_orientation = tuple(listener.rotation_quaternion)
    bpy.ops.wm.pong_handler()


if __name__ == "__main__":
    main()
