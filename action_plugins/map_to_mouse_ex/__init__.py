# -*- coding: utf-8; -*-

# MaptoMouseEx - enhanced version of MapToMouse


import logging
import math
import os
from xml.etree import ElementTree

from PySide6 import QtCore, QtWidgets

from gremlin.base_classes import AbstractAction, AbstractFunctor
from gremlin.common import InputType, MouseButton
from gremlin.profile import read_bool, safe_read, safe_format
from gremlin.util import rad2deg
import gremlin.ui.common
import gremlin.ui.input_item
import gremlin.sendinput
from gremlin import input_devices
import enum, threading,time, random

syslog = logging.getLogger("system")


class MouseAction(enum.Enum):
    MouseButton = 0 # output a mouse button
    MouseMotion = 1 # output a mouse motion
    MouseWiggleOn = 2 # enable mouse wiggle
    MouseWiggleOff = 3 # disable mouse wiggle


    @staticmethod
    def to_string(mode):
        return mode.name
    
    def __str__(self):
        return str(self.value)
    
    @classmethod
    def _missing_(cls, name):
        for item in cls:
            if item.name.lower() == name.lower():
                return item
            return cls.MouseAction
        
    @staticmethod
    def from_string(str):
        ''' converts from a string representation (text or numeric) to the enum, not case sensitive'''
        str = str.lower().strip()
        if str.isnumeric():
            mode = int(str)
            return MouseAction(mode)
        for item in MouseAction:
            if item.name.lower() == str:
                return item

        return None
    
    @staticmethod
    def to_description(action):
        ''' returns a descriptive string for the action '''
        if action == MouseAction.MouseButton:
            return "Maps a mouse button"
        elif action == MouseAction.MouseMotion:
            return "Maps to a mouse motion axis"
        elif action == MouseAction.MouseWiggleOff:
            return "Turns wiggle mode off"
        elif action == MouseAction.MouseWiggleOn:
            return "Turns wiggle mode on"
        
        return f"Unknown {action}"
    
    @staticmethod
    def to_name(action):
        ''' returns the name from the action '''
        if action == MouseAction.MouseButton:
            return "Mouse button"
        elif action == MouseAction.MouseMotion:
            return "Mouse axis"
        elif action == MouseAction.MouseWiggleOff:
            return "Wiggle Disable"
        elif action == MouseAction.MouseWiggleOn:
            return "Wiggle Enable"
        return f"Unknown {action}"

class MapToMouseExWidget(gremlin.ui.input_item.AbstractActionWidget):

    """UI widget for mapping inputs to mouse motion or buttons."""

    def __init__(self, action_data, parent=None):
        """Creates a new instance.

        :param action_data the data managed by this widget
        :param parent the parent of this widget
        """
        super().__init__(action_data, QtWidgets.QVBoxLayout, parent=parent)

        

    def _create_ui(self):
        """Creates the UI components."""
        # Layouts to use
        self.mode_layout = QtWidgets.QHBoxLayout()

        self.button_widget = QtWidgets.QWidget()
        self.button_layout = QtWidgets.QGridLayout(self.button_widget)
        self.motion_widget = QtWidgets.QWidget()
        self.motion_layout = QtWidgets.QGridLayout(self.motion_widget)
        self.release_widget = QtWidgets.QWidget() 
        self.release_layout = QtWidgets.QHBoxLayout(self.release_widget)



        self.mode_widget = gremlin.ui.common.NoWheelComboBox()

        input_type = self._get_input_type()
        if input_type == InputType.JoystickButton:
            actions = (a for a in MouseAction)
        else:
            actions = (MouseAction.MouseButton, MouseAction.MouseMotion)
        
        for mode in actions:
            self.mode_widget.addItem(MouseAction.to_name(mode), mode)

        self.mode_label = QtWidgets.QLabel("Description")

        self.mode_widget.currentIndexChanged.connect(self._action_mode_changed)


        self.chkb_exec_on_release = QtWidgets.QCheckBox("Exec on release")
        self.chkb_exec_on_release.clicked.connect(self._exec_on_release_changed)
        self.release_layout.addWidget(self.chkb_exec_on_release)

        # self.button_group = QtWidgets.QButtonGroup()
        # self.button_radio = QtWidgets.QRadioButton("Button")
        # self.motion_radio = QtWidgets.QRadioButton("Motion")
        # self.wiggle_start_radio = QtWidgets.QRadioButton("Wiggle Start")
        # self.wiggle_stop_radio = QtWidgets.QRadioButton("Wiggle Stop")
        # self.button_group.addButton(self.button_radio)
        # self.button_group.addButton(self.motion_radio)

        self.mode_layout.addWidget(self.mode_widget)
        self.mode_layout.addWidget(self.mode_label)
        self.mode_layout.addStretch()

        # self.mode_layout.addWidget(self.wiggle_start_radio)
        # self.mode_layout.addWidget(self.wiggle_stop_radio)

        # self.button_radio.clicked.connect(self._change_mode)
        # self.motion_radio.clicked.connect(self._change_mode)
        

        self.button_widget.hide()
        self.motion_widget.hide()


        self.main_layout.addLayout(self.mode_layout)
        self.main_layout.addWidget(self.release_widget)
        self.main_layout.addWidget(self.button_widget)
        self.main_layout.addWidget(self.motion_widget)


        # Create the different UI elements
        self._create_mouse_button_ui()
        if self.action_data.get_input_type() == InputType.JoystickAxis:
            self._create_axis_ui()
        else:
            self._create_button_hat_ui()



    def _create_axis_ui(self):
        """Creates the UI for axis setups."""
        self.x_axis = QtWidgets.QRadioButton("X Axis")
        self.x_axis.setChecked(True)
        self.y_axis = QtWidgets.QRadioButton("Y Axis")

        self.motion_layout.addWidget(
            QtWidgets.QLabel("Control"),
            0,
            0,
            QtCore.Qt.AlignLeft
        )
        self.motion_layout.addWidget(self.x_axis, 0, 1, QtCore.Qt.AlignLeft)
        self.motion_layout.addWidget(self.y_axis, 0, 2, 1, 2, QtCore.Qt.AlignLeft)

        self.min_speed = QtWidgets.QSpinBox()
        self.min_speed.setRange(0, 1e5)
        self.max_speed = QtWidgets.QSpinBox()
        self.max_speed.setRange(0, 1e5)
        self.motion_layout.addWidget(
            QtWidgets.QLabel("Minimum speed"), 1, 0, QtCore.Qt.AlignLeft
        )
        self.motion_layout.addWidget(self.min_speed, 1, 1, QtCore.Qt.AlignLeft)
        self.motion_layout.addWidget(
            QtWidgets.QLabel("Maximum speed"), 1, 2, QtCore.Qt.AlignLeft
        )
        self.motion_layout.addWidget(self.max_speed, 1, 3, QtCore.Qt.AlignLeft)

        self._connect_axis()

    def _create_button_hat_ui(self):
        """Creates the UI for button setups."""
        self.min_speed = QtWidgets.QSpinBox()
        self.min_speed.setRange(0, 1e5)
        self.max_speed = QtWidgets.QSpinBox()
        self.max_speed.setRange(0, 1e5)
        self.time_to_max_speed = gremlin.ui.common.DynamicDoubleSpinBox()
        self.time_to_max_speed.setRange(0.0, 100.0)
        self.time_to_max_speed.setValue(0.0)
        self.time_to_max_speed.setDecimals(2)
        self.time_to_max_speed.setSingleStep(0.1)
        self.direction = QtWidgets.QSpinBox()
        self.direction.setRange(0, 359)

        self.motion_layout.addWidget(QtWidgets.QLabel("Minimum speed"), 0, 0)
        self.motion_layout.addWidget(self.min_speed, 0, 1, QtCore.Qt.AlignLeft)
        self.motion_layout.addWidget(QtWidgets.QLabel("Maximum speed"), 0, 2)
        self.motion_layout.addWidget(self.max_speed, 0, 3, QtCore.Qt.AlignLeft)

        self.motion_layout.addWidget(
            QtWidgets.QLabel("Time to maximum speed"), 1, 0
        )
        self.motion_layout.addWidget(
            self.time_to_max_speed, 1, 1, QtCore.Qt.AlignLeft
        )
        if self.action_data.get_input_type() in [
            InputType.JoystickButton, InputType.Keyboard
        ]:
            self.motion_layout.addWidget(QtWidgets.QLabel("Direction"), 1, 2)
            self.motion_layout.addWidget(
                self.direction, 1, 3, QtCore.Qt.AlignLeft
            )

        self._connect_button_hat()

    def _create_mouse_button_ui(self):
        self.mouse_button = gremlin.ui.common.NoKeyboardPushButton(
            gremlin.common.MouseButton.to_string(self.action_data.button_id)
        )
        self.mouse_button.clicked.connect(self._request_user_input)

        self.button_layout.addWidget(QtWidgets.QLabel("Mouse Button"), 0, 0)
        self.button_layout.addWidget(self.mouse_button, 0, 1)

    def _populate_ui(self):
        """Populates the UI components."""
        input_type = self.action_data.get_input_type()
        if input_type == InputType.JoystickAxis:
            self._populate_axis_ui()
        else:
            self._populate_button_hat_ui()
        self._populate_mouse_button_ui()


        with QtCore.QSignalBlocker(self.chkb_exec_on_release):
            self.chkb_exec_on_release.setChecked(self.action_data.exec_on_release)

        action_mode = self.action_data.action_mode 
        index = self.mode_widget.findData(action_mode)
        if index != -1 and self.mode_widget.currentIndex != index:
            with QtCore.QSignalBlocker(self.mode_widget):
                self.mode_widget.setCurrentIndex(index)

        # self.motion_radio.setChecked(action_mode == MouseAction.MouseMotion)
        # self.button_radio.setChecked(action_mode == MouseAction.MouseButton)
        
        self.mode_label.setText(MouseAction.to_description(action_mode))

        self._change_mode()

    def _populate_axis_ui(self):
        """Populates axis UI elements with data."""
        self._disconnect_axis()
        if self.action_data.direction == 90:
            self.x_axis.setChecked(True)
        else:
            self.y_axis.setChecked(True)

        self.min_speed.setValue(self.action_data.min_speed)
        self.max_speed.setValue(self.action_data.max_speed)
        self._connect_axis()

    def _populate_button_hat_ui(self):
        """Populates button UI elements with data."""
        self._disconnect_button_hat()
        self.min_speed.setValue(self.action_data.min_speed)
        self.max_speed.setValue(self.action_data.max_speed)
        self.time_to_max_speed.setValue(self.action_data.time_to_max_speed)
        self.direction.setValue(self.action_data.direction)
        self._connect_button_hat()

    def _populate_mouse_button_ui(self):
        self.mouse_button.setText(
            gremlin.common.MouseButton.to_string(self.action_data.button_id)
        )

    def _action_mode_changed(self, index):  
        ''' called when the action mode drop down value changes '''
        with QtCore.QSignalBlocker(self.mode_widget):
            action = self.mode_widget.itemData(index)
            self.action_data.action_mode = action
            self._change_mode()  

    def _exec_on_release_changed(self, value):
        self.action_data.exec_on_release = self.chkb_exec_on_release.isChecked()
                

    def _update_axis(self):
        """Updates the axis data with UI information."""
        self._disconnect_axis()

        # Update speed values
        min_speed = self.min_speed.value()
        max_speed = self.max_speed.value()
        if min_speed > max_speed:
            # Maximum value was decreased below minimum
            if max_speed != self.action_data.max_speed:
                min_speed = max_speed
            # Minimum value was increased above maximum
            elif min_speed != self.action_data.min_speed:
                max_speed = min_speed
        self.min_speed.setValue(min_speed)
        self.max_speed.setValue(max_speed)

        self.action_data.direction = 90 if self.x_axis.isChecked() else 0
        self.action_data.min_speed = min_speed
        self.action_data.max_speed = max_speed

        self._connect_axis()

    def _update_button_hat(self):
        """Updates the button data with UI information."""
        self._disconnect_button_hat()

        # Update speed values
        min_speed = self.min_speed.value()
        max_speed = self.max_speed.value()
        if min_speed > max_speed:
            # Maximum value was decreased below minimum
            if max_speed != self.action_data.max_speed:
                min_speed = max_speed
            # Minimum value was increased above maximum
            elif min_speed != self.action_data.min_speed:
                max_speed = min_speed
        self.min_speed.setValue(min_speed)
        self.max_speed.setValue(max_speed)

        self.action_data.min_speed = min_speed
        self.action_data.max_speed = max_speed
        self.action_data.time_to_max_speed = self.time_to_max_speed.value()
        self.action_data.direction = self.direction.value()

        self._connect_button_hat()

    def _update_mouse_button(self, event):
        self.action_data.button_id = event.identifier
        self.mouse_button.setText(
            gremlin.common.MouseButton.to_string(self.action_data.button_id)
        )

    def _connect_axis(self):
        """Connects all axis input elements to their callbacks."""
        self.x_axis.toggled.connect(self._update_axis)
        self.y_axis.toggled.connect(self._update_axis)
        self.min_speed.valueChanged.connect(self._update_axis)
        self.max_speed.valueChanged.connect(self._update_axis)

    def _disconnect_axis(self):
        """Disconnects all axis input elements from their callbacks."""
        self.x_axis.toggled.disconnect(self._update_axis)
        self.y_axis.toggled.disconnect(self._update_axis)
        self.min_speed.valueChanged.disconnect(self._update_axis)
        self.max_speed.valueChanged.disconnect(self._update_axis)

    def _connect_button_hat(self):
        """Connects all button input elements to their callbacks."""
        self.min_speed.valueChanged.connect(self._update_button_hat)
        self.max_speed.valueChanged.connect(self._update_button_hat)
        self.time_to_max_speed.valueChanged.connect(self._update_button_hat)
        self.direction.valueChanged.connect(self._update_button_hat)

    def _disconnect_button_hat(self):
        """Disconnects all button input elements to their callbacks."""
        self.min_speed.valueChanged.disconnect(self._update_button_hat)
        self.max_speed.valueChanged.disconnect(self._update_button_hat)
        self.time_to_max_speed.valueChanged.disconnect(self._update_button_hat)
        self.direction.valueChanged.disconnect(self._update_button_hat)

    def _change_mode(self):
        self.action_data.motion_input = False
        show_button = False
        show_motion = False
        show_release = False

        if self.action_data.get_input_type() == InputType.JoystickButton:
            show_release = True

        action_mode = self.action_data.action_mode
        if action_mode == MouseAction.MouseButton:
            show_button = True
        elif action_mode == MouseAction.MouseMotion:
            show_motion = True

        self.action_data.motion_input = show_motion
        
        
        # if self.motion_radio.isChecked():
        #     self.action_data.action_mode = MouseAction.MouseMotion
        #     self.action_data.motion_input = True
        #     show_motion = True
        # elif self.button_radio.isChecked():
        #     self.action_data.action_mode  = MouseAction.MouseButton
        #     show_button = True
        # elif self.wiggle_start_radio.isChecked():
        #     self.action_data.action_mode  = MouseAction.MouseWiggleOn
        # elif self.wiggle_stop_radio.isChecked():
        #     self.action_data.action_mode  = MouseAction.MouseWiggleOff
            
        #show_motion = self.action_data.motion_input
        self.motion_widget.setVisible(show_motion)
        self.button_widget.setVisible(show_button)
        self.chkb_exec_on_release.setVisible(show_release)

        # if self.action_data.motion_input:
        #     self.button_widget.hide()
        #     self.motion_widget.show()
        # else:
        #     self.button_widget.show()
        #     self.motion_widget.hide()

        # Emit modification signal to ensure virtual button settings
        # are updated correctly
        self.action_modified.emit()

    def _request_user_input(self):
        """Prompts the user for the input to bind to this item."""
        self.button_press_dialog = gremlin.ui.common.InputListenerWidget(
            self._update_mouse_button,
            [InputType.Mouse],
            return_kb_event=False
        )

        # Display the dialog centered in the middle of the UI
        root = self
        while root.parent():
            root = root.parent()
        geom = root.geometry()

        self.button_press_dialog.setGeometry(
            int(geom.x() + geom.width() / 2 - 150),
            int(geom.y() + geom.height() / 2 - 75),
            300,
            150
        )
        self.button_press_dialog.show()


class MapToMouseExFunctor(AbstractFunctor):

    """Implements the functionality required to move a mouse cursor.

    This moves the mouse cursor by issuing relative motion commands. This is
    only implemented for axis and hat inputs as they can control a cursor
    properly with a single input, at least partially.
    """

    # shared wiggle thread
    _wiggle_thread = None
    _wiggle_stop_requested = False
    _mouse_controller = None


    def __init__(self, action):
        """Creates a new functor with the provided data.

        :param action contains parameters to use with the functor
        """
        super().__init__(action)

        self.action = action
        if not MapToMouseExFunctor._mouse_controller:
            MapToMouseExFunctor._mouse_controller = gremlin.sendinput.MouseController()
        
        self.input_type = action.input_type
        self.exec_on_release = action.exec_on_release
        self.action_mode = action.action_mode
        #syslog.debug(f"Init mouse functor event: {self.action_mode.name} {action.action_id} exec on release: {action.exec_on_release}")
        # if action.exec_on_release:
        #     pass
        

    

    def process_event(self, event, value):
        ''' processes an input event - must return True on success, False to abort the input sequence '''

        #syslog.debug(f"Process mouse functor event: {self.action_mode.name}  {self.action.action_id} exec on release: {self.action.exec_on_release}")
        if self.input_type == InputType.JoystickButton:

            if self.action_mode == MouseAction.MouseWiggleOn:
                # start the wiggle thread
                if self.exec_on_release and not event.is_pressed:
                        self._wiggle_start()
                        syslog.debug("Wiggle start requested (exec on release)")
                elif not self.exec_on_release and event.is_pressed:
                    self._wiggle_start()
                    syslog.debug("Wiggle start requested")
            elif self.action_mode == MouseAction.MouseWiggleOff:
                if self.exec_on_release and not event.is_pressed:
                        syslog.debug("Wiggle stop requested (exec on release)")
                        self._wiggle_stop()
                elif not self.exec_on_release and event.is_pressed:
                    syslog.debug("Wiggle stop requested")
                    self._wiggle_stop()

            
        elif self.action_mode == MouseAction.MouseMotion:
            if event.event_type == InputType.JoystickAxis:
                self._perform_axis_motion(event, value)
            elif event.event_type == InputType.JoystickHat:
                self._perform_hat_motion(event, value)
            else:
                self._perform_button_motion(event, value)
        elif self.action_mode == MouseAction.MouseButton:
            self._perform_mouse_button(event, value)

        return True

    def _perform_mouse_button(self, event, value):
        assert self.action.motion_input is False
        (is_local, is_remote) = input_devices.remote_state.state
        if self.action.button_id in [MouseButton.WheelDown, MouseButton.WheelUp]:
            if value.current:
                direction = -16
                if self.action.button_id == MouseButton.WheelDown:
                    direction = 1
                if is_local:
                    gremlin.sendinput.mouse_wheel(direction)
                if is_remote:
                    input_devices.remote_client.send_mouse_wheel(direction)
        else:
            if value.current:
                if is_local:
                    gremlin.sendinput.mouse_press(self.action.button_id)
                if is_remote:
                    input_devices.remote_client.send_mouse_button(self.action.button_id.value, True)
            else:
                if is_local:
                    gremlin.sendinput.mouse_release(self.action.button_id)
                if is_remote:
                    input_devices.remote_client.send_mouse_button(self.action.button_id.value, False)

        

    def _perform_axis_motion(self, event, value):
        """Processes events destined for an axis.

        :param event the event triggering the code execution
        :param value the current value of the event chain
        """
        delta_motion = self.action.min_speed + abs(value.current) * \
                (self.action.max_speed - self.action.min_speed)
        delta_motion = math.copysign(delta_motion, value.current)
        delta_motion = 0.0 if abs(value.current) < 0.05 else delta_motion

        dx = delta_motion if self.action.direction == 90 else None
        dy = delta_motion if self.action.direction != 90 else None
        (is_local, is_remote) = input_devices.remote_state.state
        if is_local:
            MapToMouseExFunctor._mouse_controller.set_absolute_motion(dx, dy)
        if is_remote:
            input_devices.remote_client.send_mouse_motion(dx, dy)

    def _perform_button_motion(self, event, value):
        (is_local, is_remote) = input_devices.remote_state.state
        if event.is_pressed:
            if is_local:
                MapToMouseExFunctor._mouse_controller.set_accelerated_motion(
                    self.action.direction,
                    self.action.min_speed,
                    self.action.max_speed,
                    self.action.time_to_max_speed
                )
            if is_remote:
                input_devices.remote_client.send_mouse_acceleration(self.action.direction, self.action.min_speed, self.action.max_speed, self.action.time_to_max_speed)
     
        else:
            if is_local:
                MapToMouseExFunctor._mouse_controller.set_absolute_motion(0, 0)
            if is_remote:
                input_devices.remote_client.send_mouse_motion(0, 0)

    def _perform_hat_motion(self, event, value):
        """Processes events destined for a hat.

        :param event the event triggering the code execution
        :param value the current value of the event chain
        """
        is_local = input_devices.remote_client.is_local
        is_remote = input_devices.remote_client.is_remote
        if value.current == (0, 0):
            if is_local:
                MapToMouseExFunctor._mouse_controller.set_absolute_motion(0, 0)
            if is_remote:
                input_devices.remote_client.send_mouse_motion(0, 0)

        else:
            a = rad2deg(math.atan2(-value.current[1], value.current[0])) + 90.0
            if is_local:
                MapToMouseExFunctor._mouse_controller.set_accelerated_motion(
                    a,
                    self.action.min_speed,
                    self.action.max_speed,
                    self.action.time_to_max_speed
                )
            if is_remote:
                input_devices.remote_client.send_mouse_acceleration(a, self.action.min_speed, self.action.max_speed, self.action.time_to_max_speed)


    def _wiggle_start(self):
        ''' starts the wiggle thread '''
        if MapToMouseExFunctor._wiggle_thread:
            # already started
            return 
        MapToMouseExFunctor._wiggle_stop_requested = False
        MapToMouseExFunctor._wiggle_thread = threading.Thread(target=MapToMouseExFunctor._wiggle)
        MapToMouseExFunctor._wiggle_thread.start()

    def _wiggle_stop(self):
        ''' stops the wiggle thread '''
        if not MapToMouseExFunctor._wiggle_thread:
            # already started
            return 
        syslog.debug("Wiggle stop requested...")
        MapToMouseExFunctor._wiggle_stop_requested = True
        MapToMouseExFunctor._wiggle_thread.join()
        syslog.debug("Wiggle thread exited...")
        MapToMouseExFunctor._wiggle_thread = None

    @staticmethod
    def _wiggle():
        ''' wiggles the mouse '''
        syslog.debug("Wiggle start...")
        (is_local, is_remote) = input_devices.remote_state.state
        t_wait = time.time()
        while not MapToMouseExFunctor._wiggle_stop_requested:
            if time.time() >= t_wait:
                syslog.debug("wiggling...")
                if is_local:
                    MapToMouseExFunctor._mouse_controller.set_absolute_motion(1, 1)
                    time.sleep(1)
                    MapToMouseExFunctor._mouse_controller.set_absolute_motion(-1, -1)
                    time.sleep(0.5)
                    MapToMouseExFunctor._mouse_controller.set_absolute_motion(0, 0)
                if is_remote:
                    input_devices.remote_client.send_mouse_motion(1, 1)
                    time.sleep(1)
                    input_devices.remote_client.send_mouse_motion(-1, -1)
                    time.sleep(0.5)
                    input_devices.remote_client.send_mouse_motion(0,0)
                t_wait = time.time() + random.uniform(10,40)
            time.sleep(0.5)
            
        syslog.debug("Wiggle stop...")


class MapToMouseEx(AbstractAction):

    """Action data for the map to mouse action.

    Map to mouse allows controlling of the mouse cursor using either a joystick
    or a hat.
    """

    name = "Map to Mouse EX"
    tag = "map_to_mouse_ex"

    default_button_activation = (True, True)
    input_types = [
        InputType.JoystickAxis,
        InputType.JoystickButton,
        InputType.JoystickHat,
        InputType.Keyboard
    ]

    functor = MapToMouseExFunctor
    widget = MapToMouseExWidget

    def __init__(self, parent):
        """Creates a new instance.

        :param parent the container this action is part of
        """
        super().__init__(parent)

        # Flag whether or not this is mouse motion or button press
        self.motion_input = False
        # Mouse button enum
        self.button_id = gremlin.common.MouseButton.Left
        # Angle of motion, 0 is up and 90 is right, etc.
        self.direction = 0
        # Minimum motion speed in pixels / sec
        self.min_speed = 5
        # Maximum motion speed in pixels / sec
        self.max_speed = 15
        # Time to reach maximum speed in sec
        self.time_to_max_speed = 1.0

        self.action_mode = MouseAction.MouseButton
        self.exec_on_release = False
        self.input_type = InputType.JoystickButton


    def icon(self):
        """Returns the icon to use for this action.

        :return icon representing this action
        """
        return "{}/icon.png".format(os.path.dirname(os.path.realpath(__file__)))

    def requires_virtual_button(self):
        """Returns whether or not an activation condition is needed.

        :return True if an activation condition is required for this particular
            action instance, False otherwise
        """
        # Need virtual buttons for button inputs on axes and hats
        if self.get_input_type() in [InputType.JoystickAxis, InputType.JoystickHat]:
            return not self.motion_input
        return False

    def _parse_xml(self, node):
        """Reads the contents of an XML node to populate this instance.

        :param node the node whose content should be used to populate this
            instance
        """

        self.action_mode = MouseAction.from_string(safe_read(node, "mode", str, "mousebutton"))

        self.motion_input = read_bool(node, "motion-input", False)
        try:
            self.button_id = gremlin.common.MouseButton(
                safe_read(node, "button-id", int, 1)
            )
        except ValueError as e:
            logging.getLogger("system").warning(
                "Invalid mouse identifier in profile: {:}".format(e)
            )
            self.button_id = gremlin.common.MouseButton.Left

        self.direction = safe_read(node, "direction", int, 0)
        self.min_speed = safe_read(node, "min-speed", int, 5)
        self.max_speed = safe_read(node, "max-speed", int, 5)
        self.time_to_max_speed = safe_read(node, "time-to-max-speed", float, 0.0)

        # get the type of mapping this is
        
        
        if "exec_on_release" in node.attrib:
            self.exec_on_release = safe_read(node,"exec_on_release",bool, False)

    def _generate_xml(self):
        """Returns an XML node containing this instance's information.

        :return XML node containing the information of this  instance
        """
        node = ElementTree.Element(MapToMouseEx.tag)

        node.set("mode", self.action_mode.name)
        node.set("motion-input", safe_format(self.motion_input, bool))
        node.set("button-id", safe_format(self.button_id.value, int))
        node.set("direction", safe_format(self.direction, int))
        node.set("min-speed", safe_format(self.min_speed, int))
        node.set("max-speed", safe_format(self.max_speed, int))
        node.set("time-to-max-speed", safe_format(self.time_to_max_speed, float))
        node.set("exec_on_release", safe_format(self.exec_on_release, bool))

        return node

    def _is_valid(self):
        """Returns whether or not this action is valid.

        :return True if the action is configured correctly, False otherwise
        """
        return True


version = 1
name = "map_to_mouse_ex"
create = MapToMouseEx
