#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import httplib
import json

import ConfigParser
import pytest
from py.xml import html
from selenium import selenium
from selenium import webdriver

import selenium_client


class Client(selenium_client.Client):

    def __init__(self, test_id, options, keywords, credentials):
        super(Client, self).__init__(test_id, options)

        self.browser_name = options.browser_name
        self.browser_version = options.browser_version
        self.platform = options.platform
        self.platform_version = options.platform_version
        self.device_name = options.device_name
        self.appium = options.appium_version
        #added options
        self.max_duration = options.max_duration  # max test duration
        self.command_timeout = options.command_timeout  # max time to wait for command to finish
        self.idle_timeout = options.idle_timeout  # max time to wait for new command

        self.keywords = keywords
        self.build = options.build
        self.credentials = credentials

    def check_basic_usage(self):
        super(Client, self).check_basic_usage()

        if not self.credentials['username']:
            raise pytest.UsageError('username must be specified in the sauce labs credentials file.')

        if not self.credentials['api-key']:
            raise pytest.UsageError('api-key must be specified in the sauce labs credentials file.')

    def check_rc_usage(self):
        if not self.browser_name:
            raise pytest.UsageError("--browsername must be specified when using the 'rc' api with sauce labs.")

        if not self.platform:
            raise pytest.UsageError("--platform must be specified when using the 'rc' api with sauce labs.")

    @property
    def common_settings(self):
        config = ConfigParser.ConfigParser(defaults={
            'tags': '',
            'privacy': 'public restricted'})
        config.read('mozwebqa.cfg')
        tags = config.get('DEFAULT', 'tags').split(',')
        from _pytest.mark import MarkInfo
        tags.extend([mark for mark in self.keywords.keys() if isinstance(self.keywords[mark], MarkInfo)])
        try:
            privacy = self.keywords['privacy'].args[0]
        except (IndexError, KeyError):
            # privacy mark is not present or has no value
            privacy = config.get('DEFAULT', 'privacy')
        return {'build': self.build or None,
                'name': self.test_id,
                'tags': tags,
                'public': privacy}

    def start_webdriver_client(self):
        capabilities = self.common_settings
        if self.appium:
            capabilities.update({'platformName': self.platform,
                                'browserName': self.browser_name,
                                 'platformVersion': self.platform_version,
                                 'deviceName': self.device_name,
                                 'appiumVersion': self.appium})
        else:
            capabilities.update({'platform': self.platform,
                                 'browserName': self.browser_name})
        #handling of if sauce options set
        if self.max_duration:
            capabilities['maxDuration'] = self.max_duration
        if self.command_timeout:
            capabilities['commandTimeout'] = self.command_timeout
        if self.idle_timeout:
            capabilities['idleTimeout'] = self.idle_timeout

        if self.browser_version:
            capabilities['version'] = self.browser_version
        for c in self.capabilities:
            name, value = c.split(':')
            # handle integer capabilities
            if value.isdigit():
                value = int(value)
            # handle boolean capabilities
            elif value.lower() in ['true', 'false']:
                value = value.lower() == 'true'
            capabilities.update({name: value})
        executor = 'http://%s:%s@ondemand.saucelabs.com:80/wd/hub' % (
            self.credentials['username'],
            self.credentials['api-key'])
        self.selenium = webdriver.Remote(command_executor=executor,
                                         desired_capabilities=capabilities)

    def start_rc_client(self):
        settings = self.common_settings
        settings.update({'username': self.credentials['username'],
                         'access-key': self.credentials['api-key'],
                         'os': self.platform,
                         'browser': self.browser_name})
        if self.browser_version:
            settings['browser-version'] = self.browser_version
        self.selenium = selenium('ondemand.saucelabs.com', '80',
                                 json.dumps(settings),
                                 self.base_url)
        self.selenium.start()


class Job(object):

    def __init__(self, session_id):
        self.session_id = session_id

    @property
    def url(self):
        return 'http://saucelabs.com/jobs/%s' % self.session_id

    @property
    def video_html(self):
        flash_vars = 'config={\
            "clip":{\
                "url":"https%%3A//saucelabs.com/jobs/%(session_id)s/video.flv",\
                "provider":"streamer",\
                "autoPlay":false,\
                "autoBuffering":true},\
            "plugins":{\
                "streamer":{\
                    "url":"https://saucelabs.com/flowplayer/flowplayer.pseudostreaming-3.2.5.swf"},\
                "controls":{\
                    "mute":false,\
                    "volume":false,\
                    "backgroundColor":"rgba(0, 0, 0, 0.7)"}},\
            "playerId":"player%(session_id)s",\
            "playlist":[{\
                "url":"https%%3A//saucelabs.com/jobs/%(session_id)s/video.flv",\
                "provider":"streamer",\
                "autoPlay":false,\
                "autoBuffering":true}]}' % {'session_id': self.session_id}

        return html.div(html.object(
            html.param(value='true', name='allowfullscreen'),
            html.param(value='always', name='allowscriptaccess'),
            html.param(value='high', name='quality'),
            html.param(value='true', name='cachebusting'),
            html.param(value='#000000', name='bgcolor'),
            html.param(
                value=flash_vars.replace(' ', ''),
                name='flashvars'),
            width='100%',
            height='100%',
            type='application/x-shockwave-flash',
            data='https://saucelabs.com/flowplayer/flowplayer-3.2.5.swf?0.2930636672245027',
            name='player_api',
            id='player_api'),
            id='player%s' % self.session_id,
            class_='video')

    def send_result(self, result, credentials):
        try:
            basic_authentication = (
                '%s:%s' % (credentials['username'],
                           credentials['api-key'])).encode('base64')[:-1]
            connection = httplib.HTTPConnection('saucelabs.com')
            connection.request(
                'PUT',
                '/rest/v1/%s/jobs/%s' % (credentials['username'], self.session_id),
                json.dumps(result),
                headers={'Authorization': 'Basic %s' % basic_authentication,
                         'Content-Type': 'text/json'})
            connection.getresponse()
        except:
            pass
