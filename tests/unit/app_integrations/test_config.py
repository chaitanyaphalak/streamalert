"""
Copyright 2017-present, Airbnb Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
# pylint: disable=no-self-use,protected-access
from mock import patch
from nose.tools import assert_equal, assert_false, assert_items_equal, raises

from app_integrations.config import AppConfig
from app_integrations.exceptions import AppIntegrationConfigError
from tests.unit.app_integrations import FUNCTION_NAME
from tests.unit.app_integrations.test_helpers import (
    get_mock_context,
    MockSSMClient
)

MOCK_SSM = MockSSMClient()


@patch.object(AppConfig, 'SSM_CLIENT', MOCK_SSM)
class TestAppIntegrationConfig(object):
    """Test class for AppIntegrationConfig"""

    def __init__(self):
        self._config = None

    @patch.object(AppConfig, 'SSM_CLIENT', MOCK_SSM)
    def setup(self):
        """Setup before each method"""
        self._config = AppConfig.load_config(get_mock_context())

    def test_parse_context(self):
        """AppIntegrationConfig - Parse Context"""
        mock_context = get_mock_context()
        result = AppConfig._parse_context(mock_context)

        assert_equal(AppConfig.remaining_ms, mock_context.get_remaining_time_in_millis)
        assert_equal(AppConfig.remaining_ms(), 100)
        assert_equal(result['function_name'], FUNCTION_NAME)

    def test_load_config(self):
        """AppIntegrationConfig - Load config from SSM"""
        assert_equal(len(self._config.keys()), 12)

    @raises(AppIntegrationConfigError)
    def test_load_config_bad(self):
        """AppIntegrationConfig - Load config from SSM, missing key"""
        # Remove one of the required keys from the state
        del self._config['qualifier']
        self._config._validate_config()

    @raises(AppIntegrationConfigError)
    def test_load_config_empty(self):
        """AppIntegrationConfig - Load config from SSM, empty config"""
        # Empty the config so the dict validates to False
        self._config.clear()
        self._config._validate_config()

    def test_get_param(self):
        """AppIntegrationConfig - Get parameter"""
        param, _ = AppConfig._get_parameters(['{}_config'.format(FUNCTION_NAME)])

        assert_items_equal(param['{}_config'.format(FUNCTION_NAME)].keys(),
                           {'cluster', 'app_name', 'type', 'prefix', 'interval'})

    @raises(AppIntegrationConfigError)
    def test_get_param_bad_value(self):
        """AppIntegrationConfig - Get parameter, bad json value"""
        config_name = '{}_config'.format(FUNCTION_NAME)
        with patch.dict(AppConfig.SSM_CLIENT._parameters, {config_name: 'bad json'}):
            AppConfig._get_parameters([config_name])

    @raises(AppIntegrationConfigError)
    def test_evaluate_interval_no_interval(self):
        """AppIntegrationConfig - Evaluate Interval, No Interval"""
        del self._config['interval']
        self._config.evaluate_interval()

    @raises(AppIntegrationConfigError)
    def test_evaluate_interval_invalid(self):
        """AppIntegrationConfig - Evaluate Interval, Invalid Interval"""
        self._config['interval'] = 'rate(1 hours)'
        self._config.evaluate_interval()

    def test_evaluate_interval(self):
        """AppIntegrationConfig - Evaluate Interval"""
        self._config['interval'] = 'rate(5 hours)'
        assert_equal(self._config.evaluate_interval(), 3600 * 5)

    @patch('time.mktime')
    def test_determine_last_timestamp(self, time_mock):
        """AppIntegrationConfig - Determine Last Timestamp"""
        # Reset the last timestamp to None
        self._config.last_timestamp = None

        # Use a mocked current time
        current_time = 1234567890
        time_mock.return_value = current_time
        self._config['interval'] = 'rate(5 hours)'
        assert_equal(self._config._determine_last_time(), 1234567890 - (3600 * 5))

    @patch('logging.Logger.error')
    def test_set_item(self, log_mock):
        """AppIntegrationConfig - Set Item, Bad Value"""
        bad_state = 'bad value'
        self._config['current_state'] = bad_state
        log_mock.assert_called_with('Current state cannot be saved with value \'%s\'', bad_state)

    def test_mark_failure(self):
        """AppIntegrationConfig - Mark Failure"""
        self._config.mark_failure()
        assert_equal(self._config['current_state'], 'failed')

    def test_is_failing(self):
        """AppIntegrationConfig - Check If Failing"""
        assert_false(self._config.is_failing)

    def test_scrub_auth_info(self):
        """AppIntegrationConfig - Scrub Auth Info"""
        auth_key = '{}_auth'.format(FUNCTION_NAME)
        param_dict = {auth_key: self._config['auth']}
        scrubbed_config = self._config._scrub_auth_info(param_dict, auth_key)
        assert_equal(scrubbed_config[auth_key]['api_hostname'],
                     '*' * len(self._config['auth']['api_hostname']))
        assert_equal(scrubbed_config[auth_key]['integration_key'],
                     '*' * len(self._config['auth']['integration_key']))
        assert_equal(scrubbed_config[auth_key]['secret_key'],
                     '*' * len(self._config['auth']['secret_key']))
