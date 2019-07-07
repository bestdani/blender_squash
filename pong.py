import random

import bpy
import math


class PlayArea:
    def __init__(self, size):
        self.x_range = self._range_from_size(size[0])
        self.y_range = self._range_from_size(size[1])
        self.z_range = self._range_from_size(size[2])

    @staticmethod
    def _range_from_size(size_dimension):
        return -size_dimension / 2, size_dimension / 2


class Ball:
    def __init__(self, blender_object, spawn_jitter=(3, 3, 3)):
        self.size = (
            blender_object.dimensions[0],
            blender_object.dimensions[1],
            blender_object.dimensions[2])
        self.x_range = (0, 0)
        self.y_range = (0, 0)
        self.z_range = (0, 0)
        self.spawn_jitter = spawn_jitter
        self.bound_location = blender_object.location

        self.speed = 0
        self.direction = [0, 0, 0]
        self.position = [0, 0, 0]
        self.mover = None

    def spawn(self, speed):
        self.speed = speed
        self._set_new_position(
            (
                self.spawn_jitter[0] * (random.random() - 0.5),
                20,
                self.spawn_jitter[2] * (random.random() - 0.5),
            )
        )

        self.direction[0] = 1 * (random.random() - 0.5)
        self.direction[1] = -1
        self.direction[2] = 1 * (random.random() - 0.5)
        self._apply_normalization(self.direction)
        self._apply_factor(self.direction, speed)

    def set_mover(self, mover: 'Mover'):
        self.mover = mover

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

    def apply_movement_range_from_area(self, play_area):
        self.x_range = (
            play_area.x_range[0] + self.size[0] / 2,
            play_area.x_range[1] - self.size[0] / 2,
        )
        self.y_range = (
            play_area.y_range[0] + self.size[1] / 2,
            play_area.y_range[1] - self.size[1] / 2,
        )
        self.z_range = (
            play_area.z_range[0] + self.size[2] / 2,
            play_area.z_range[1] - self.size[2] / 2,
        )

    def update(self, time_delta):
        self._apply_wall_collision(self.direction)
        self._apply_mover_collision(self.mover, self.position, self.direction)
        self.position[0] += self.direction[0] * time_delta
        self.position[1] += self.direction[1] * time_delta
        self.position[2] += self.direction[2] * time_delta
        self._update_visible_position()

    def _apply_wall_collision(self, direction):
        if self.position[0] > self.x_range[1]:
            self.position[0] = self.x_range[1]
            direction[0] = -direction[0]

        if self.position[0] < self.x_range[0]:
            self.position[0] = self.x_range[0]
            direction[0] = -direction[0]

        if self.position[1] > self.y_range[1]:
            self.position[1] = self.y_range[1]
            direction[1] = -direction[1]

        # no backwall collision
        # if self.position[1] < self.y_range[0]:
        #     self.position[1] = self.y_range[0]
        #     direction[1] = -direction[1]

        if self.position[2] > self.z_range[1]:
            self.position[2] = self.z_range[1]
            direction[2] = -direction[2]

        if self.position[2] < self.z_range[0]:
            self.position[2] = self.z_range[0]
            direction[2] = -direction[2]

    def _apply_mover_collision(self, mover, position, direction):
        if mover.position[1] - 0.2 < position[1] < mover.position[1]:
            mover_bounds_x = (
                mover.position[0] - mover.size[0] / 2,
                mover.position[0] + mover.size[0] / 2
            )
            mover_bounds_z = (
                mover.position[2] - mover.size[1] / 2,
                mover.position[2] + mover.size[1] / 2
            )
            if (
                    mover_bounds_x[0] < position[0] < mover_bounds_x[1]
                    and mover_bounds_z[0] < position[2] < mover_bounds_z[1]
            ):
                self.position[1] = mover.position[1]
                direction[1] = -direction[1]
                mover.glow = True

        elif position[1] < mover.position[1] - 26:
            self.spawn(self.speed)
            # TODO handle fail here


class Mover:
    CMD_UP, CMD_DOWN, CMD_LEFT, CMD_RIGHT = 0, 1, 2, 3

    def __init__(self, blender_object, glow_control_object,
                 speeds=(10.0, 10.0)):
        self.glow_timer = 0
        self.glow_time = 0.3
        self.x_range_base = [0, 0]
        self.z_range_base = [0, 0]
        self.x_range = (0, 0)
        self.z_range = (0, 0)
        self.speeds = speeds
        self.bound_location = blender_object.location
        self.bound_scale = blender_object.scale
        self.bound_glow_control = glow_control_object.scale
        self.blender_object = blender_object

        self.size = [
            blender_object.dimensions[0], blender_object.dimensions[2]
        ]

        self.position = [0, self.bound_location[1], 0]
        self._glow = False

        self.command_map = {
            self.CMD_UP: self._increase_z,
            self.CMD_DOWN: self._decrease_z,
            self.CMD_LEFT: self._decrease_x,
            self.CMD_RIGHT: self._increase_x,
        }
        self.active_commands = set()

    def resize(self, factor):
        self.bound_scale[0] = factor * self.bound_scale[0]
        self.bound_scale[2] = factor * self.bound_scale[2]
        self.size[0] = self.blender_object.dimensions[0]
        self.size[1] = self.blender_object.dimensions[2]
        self.x_range = (
            self.x_range_base[0] + self.size[0] / 2,
            self.x_range_base[1] - self.size[0] / 2,
        )
        self.z_range = (
            self.z_range_base[0] + self.size[1] / 2,
            self.z_range_base[1] - self.size[1] / 2,
        )

    def apply_movement_range_from_area(self, play_area: 'PlayArea'):
        self.x_range_base[0] = play_area.x_range[0]
        self.x_range_base[1] = play_area.x_range[1]
        self.z_range_base[0] = play_area.z_range[0]
        self.z_range_base[1] = play_area.z_range[1]
        self.resize(1)

    def start_command(self, command):
        self.active_commands.add(command)

    def stop_command(self, command):
        self.active_commands.remove(command)

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
        self.position[0] += self.speeds[0] * time_delta
        if self.position[0] > self.x_range[1]:
            self.position[0] = self.x_range[1]

    def _decrease_x(self, time_delta):
        self.position[0] -= self.speeds[0] * time_delta
        if self.position[0] < self.x_range[0]:
            self.position[0] = self.x_range[0]

    def _increase_z(self, time_delta):
        self.position[2] += self.speeds[1] * time_delta
        if self.position[2] > self.z_range[1]:
            self.position[2] = self.z_range[1]

    def _decrease_z(self, time_delta):
        self.position[2] -= self.speeds[1] * time_delta
        if self.position[2] < self.z_range[0]:
            self.position[2] = self.z_range[0]

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
    def __init__(self, play_area: 'PlayArea', mover: 'Mover', ball: 'Ball'):
        mover.apply_movement_range_from_area(play_area)

        ball.apply_movement_range_from_area(play_area)
        ball.set_mover(mover)
        ball.spawn(10)

        self.ball = ball
        self.mover = mover
        self.play_area = play_area

    def update(self, time_delta):
        self.mover.update(time_delta)
        self.ball.update(time_delta)


class PongHandler(bpy.types.Operator):
    bl_idname = "wm.pong_handler"
    bl_label = "Pong Handler"
    update_rate = 1 / 30
    _timer = None
    _game = None
    command_for_key_type = None
    action_for_key_state = None

    def modal(self, context, event):
        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}

        elif event.type == 'TIMER':
            self._update(self.update_rate)

        elif event.type in self.command_for_key_type:
            self._handle_keys(event)

        return {'RUNNING_MODAL'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(
            self.update_rate, window=context.window)
        wm.modal_handler_add(self)

        play_area = self.setup_play_area("area")
        p1_mover = self.setup_mover("p1", "p1_glow_control")
        ball = self.setup_ball("ball")

        game = PongGame(play_area, p1_mover, ball)

        self.command_for_key_type = {
            'LEFT_ARROW': Mover.CMD_LEFT,
            'RIGHT_ARROW': Mover.CMD_RIGHT,
            'UP_ARROW': Mover.CMD_UP,
            'DOWN_ARROW': Mover.CMD_DOWN,
        }
        self.action_for_key_state = {
            'PRESS': game.mover.start_command,
            'RELEASE': game.mover.stop_command,
        }
        self._game = game

        return {'RUNNING_MODAL'}

    def setup_ball(self, ball_name):
        ball_obj = bpy.data.objects[ball_name]
        ball = Ball(ball_obj)
        return ball

    def setup_mover(self, mover_name, glow_control_name):
        mover_obj = bpy.data.objects[mover_name]
        glow_control_obj = bpy.data.objects[glow_control_name]
        mover = Mover(mover_obj, glow_control_obj)
        return mover

    def setup_play_area(self, area_obj_name):
        area_obj = bpy.data.objects[area_obj_name]
        area_dimension = area_obj.dimensions
        area_size = (
            area_dimension[0],
            area_dimension[1],
            area_dimension[2],
        )
        play_area = PlayArea(
            area_size
        )
        return play_area

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

    def _handle_keys(self, event):
        action = self.action_for_key_state[event.value]
        action(self.command_for_key_type[event.type])

    def _update(self, time_delta):
        self._game.update(time_delta)


def register():
    bpy.utils.register_class(PongHandler)


def unregister():
    bpy.utils.unregister_class(PongHandler)


if __name__ == "__main__":
    register()
    bpy.ops.wm.pong_handler()
