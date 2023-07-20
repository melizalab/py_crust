import json
import numpy as np
import zmq.asyncio

from .errata import pub_err
from .dispatch import Sauron
from .inform import *
from .decrypt import Component
from google.protobuf.json_format import MessageToDict
import asyncio
import logging

logger = logging.getLogger(__name__)


class Morgoth:
    def __init__(self, messenger=None):
        self.messenger = None
        self.sun = None
        self.playback = None
        if isinstance(messenger, Sauron):
            self.messenger = messenger
        else:
            self.messenger = Sauron()
        logger.state("Apparatus-class Object created. Praise Dan.")

    async def set_feeder(self, duration):
        logger.state("Setting feed duration")
        await self.messenger.command(request_type="SetParameters",
                                     component='stepper-motor',
                                     body={'timeout': duration}
                                     )

        interval_check = await self.messenger.command(request_type="GetParameters",
                                                      component='stepper-motor',
                                                      body=None)
        if interval_check.timeout != duration:
            logger.error(f"Stepper motor timeout parameter not set to {duration}")

    async def feed(self, delay=0):
        logger.state('feed() called, requesting stepper motor')
        await asyncio.sleep(delay)
        a = asyncio.create_task(self.messenger.scry(
            'stepper-motor',
            condition=lambda p: p['running'],
            failure=pub_err,
            timeout=TIMEOUT
        ))
        b = asyncio.create_task(self.messenger.command(
            request_type="ChangeState",
            component='stepper-motor',
            body={'running': True, 'direction': True}
        ))
        await asyncio.gather(a, b)
        logger.state('feeding confirmed by decide-rs, awaiting motor stop')
        await self.messenger.scry(
            'stepper-motor',
            condition=lambda pub: not pub['running'],
            failure=pub_err,
            timeout=TIMEOUT
        )
        logger.state('motor stop confirmed by decide-rs')
        return

    async def cue(self, loc, color):
        pos = peck_parse(loc, mode='l')
        logger.state(f'Requesting cue {pos}')
        a = asyncio.create_task(self.messenger.scry(
            pos,
            condition=lambda pub: pub['led_state'] == color,
            failure=pub_err,
            timeout=TIMEOUT
        ))
        b = asyncio.create_task(self.messenger.command(
            request_type="ChangeState",
            component=pos,
            body={'led_state': color}
        ))
        await asyncio.gather(a, b)
        return

    async def keep_alight(self, interval=300):
        self.sun = Sun()
        await self.messenger.command(request_type="SetParameters",
                                     component='house-light',
                                     body={'clock_interval': interval},
                                     caller=0)
        interval_check = await self.messenger.command(request_type="GetParameters",
                                                      component='house-light',
                                                      body=None,
                                                      caller=0)
        if interval_check.clock_interval != interval:
            logger.error(f"House-Light Clock Interval not set to {interval},"
                         f" got {interval_check.clock_interval}")

        while True:
            *topic, msg = await self.messenger.lighter.recv_multipart()
            logger.state(f"House-light - message received, checking")
            state, comp = topic[0].decode("utf-8").split("/")
            proto_comp = Component(state, comp)
            tstamp, state_msg = await proto_comp.from_pub(msg)
            decoded = MessageToDict(state_msg,
                                    including_default_value_fields=True,
                                    preserving_proto_field_name=True)
            self.sun.update(decoded)

    async def blip(self, duration, brightness=0):
        logger.state("Manually changing house lights")
        a = asyncio.create_task(self.messenger.scry(
            'house-light',
            condition=lambda pub: True if pub['brightness'] == brightness else False,
            failure=pub_err,
            timeout=TIMEOUT
        ))

        b = asyncio.create_task(self.messenger.command(
            request_type="ChangeState",
            component='house-light',
            body={'manual': True, 'brightness': brightness}
        ))
        await asyncio.gather(a, b)
        logger.state("Manually changing house lights confirmed by decide-rs.")

        await asyncio.sleep(duration/1000)

        logger.state("Returning house lights to cycle")
        a = asyncio.create_task(self.messenger.scry(
            'house-light',
            condition=lambda pub: not pub['manual'],
            failure=pub_err,
        ))
        b = asyncio.create_task(self.messenger.command(
            request_type="ChangeState",
            component='house-light',
            body={'manual': False, 'dyson': True}
        ))
        await asyncio.gather(a, b)
        logger.state("Returning house lights to cycle succeeded")

    async def init_playback(self, cfg, shuffle=True, replace=False, get_cues=True):
        self.playback = await JukeBox.spawn(cfg, shuffle, replace, get_cues)
        logger.state("Requesting stimuli directory change")
        await self.messenger.command(
            request_type="SetParameters",
            component='audio-playback',
            body={'audio_dir': self.playback.dir}
        )
        # The following has a higher timeout due to the blocking action of stimuli import on decide-rs
        dir_check = await self.messenger.command(
            request_type="GetParameters",
            component='audio-playback',
            body=None,
            timeout=100000
        )
        if dir_check.audio_dir != self.playback.dir:
            logger.error(f"Auditory folder mismatch: got {dir_check.audio_dir} expected {self.playback.dir}")

        self.playback.sample_rate = dir_check.sample_rate

    async def play(self, stim=None):
        if stim is None:
            stim = self.playback.stimulus
        logger.state(f"Playback of {stim} requested")
        a = asyncio.create_task(self.messenger.scry(
            'audio-playback',
            condition=lambda msg: (msg['audio_id'] == stim) & (msg['playback'] == 1),
            failure=pub_err,
            timeout=TIMEOUT
        ))
        b = asyncio.create_task(self.messenger.command(
            request_type="ChangeState",
            component='audio-playback',
            body={'audio_id': stim, 'playback': 1}
        ))
        _, pub, _ = await a
        await b

        frame_count = pub['frame_count']
        stim_duration = frame_count / self.playback.sample_rate

        handle = asyncio.create_task(self.messenger.scry(
            'audio-playback',
            condition=lambda msg: (msg['playback'] == 0),
            failure=pub_err,
            timeout=stim_duration + TIMEOUT
        ))
        return stim_duration, handle

    async def stop(self):
        a = asyncio.create_task(self.messenger.scry(
            'audio-playback',
            condition=lambda msg: (msg['playback'] == 0),
            failure=pub_err,
            timeout=TIMEOUT
        ))
        b = asyncio.create_task(self.messenger.command(
            request_type="ChangeState",
            component='audio-playback',
            body={'playback': 0}
        ))
        await b
        await a
        return


class Sun:
    def __init__(self):
        self.manual = False
        self.dyson = True
        self.brightness = 0
        self.daytime = True

    def update(self, decoded):
        logger.state("Updating House-Light from PUB")
        for key, val in decoded.items():
            setattr(self, key, val)
        return True


class JukeBox:
    def __init__(self):
        self.stimulus = None
        self.stim_data = None
        self.sample_rate = None
        self.ptr = None
        self.shuffle = True
        self.replace = False
        self.playlist = None
        self.dir = None
        self.cue_locations = None

    @classmethod
    async def spawn(cls, cfg, shuffle=True, replace=False, get_cues=True):
        logger.info("Spawning Playback Machine")
        self = JukeBox()
        with open(cfg) as file:
            cf = json.load(file)
            self.dir = cf['stimulus_root']
            self.stim_data = cf['stimuli']

        self.cue_locations = {}
        playlist = []

        logger.state("Validating and generating playlist")
        for i, stim in enumerate(self.stim_data):
            cue_loc = None
            for action, consq in stim['responses'].items():
                total = (consq['p_reward'] if 'p_reward' in consq else 0) + \
                        (consq['p_punish'] if 'p_punish' in consq else 0)
                if total > 1:
                    logger.error(f"Reward/Punish Percentage Exceed 1.0 for {action} in {stim['name']}")
                    raise
                if get_cues and ('p_reward' in consq):
                    cue_loc = peck_parse(action, 'l')
            if get_cues:
                self.cue_locations[stim['name']] = cue_loc
            playlist.append(np.repeat(i, stim['frequency']))

        self.playlist = np.array(playlist).flatten()
        if shuffle:
            np.random.shuffle(self.playlist)
        self.ptr = iter(self.playlist)
        self.replace = replace
        return self

    def next(self):
        if not self.replace:
            try:
                item = next(self.ptr)
            except StopIteration:
                if self.shuffle:
                    np.random.shuffle(self.playlist)
                self.ptr = iter(self.playlist)
                item = next(self.ptr)
        else:
            if self.shuffle:
                np.random.shuffle(self.playlist)
            self.ptr = iter(self.playlist)
            item = next(self.ptr)

        self.stimulus = self.stim_data[item]['name']
        return self.stim_data[item].copy()

    def current_cue(self):
        if self.stimulus is None:
            logger.error("Trying to determine cue but no stimulus specified. Try initiating playlist first")
            raise
        return self.cue_locations[self.stimulus]
