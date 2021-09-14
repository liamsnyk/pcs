from unittest import mock, TestCase

from pcs import stonith
from pcs.common import reports
from pcs.cli.common.errors import CmdLineInputError
from pcs.cli.common.parse_args import InputModifiers

from pcs_test.tools.misc import dict_to_modifiers


def _dict_to_modifiers(options):
    def _convert_val(val):
        if val is True:
            return ""
        return val

    return InputModifiers(
        {
            f"--{opt}": _convert_val(val)
            for opt, val in options.items()
            if val is not False
        }
    )


class SbdEnable(TestCase):
    def setUp(self):
        self.lib = mock.Mock(spec_set=["sbd"])
        self.sbd = mock.Mock(spec_set=["enable_sbd"])
        self.lib.sbd = self.sbd

    def assert_called_with(
        self, default_watchdog, watchdog_dict, sbd_options, **kwargs
    ):
        default_kwargs = dict(
            default_device_list=None,
            node_device_dict=None,
            allow_unknown_opts=False,
            ignore_offline_nodes=False,
            no_watchdog_validation=False,
        )
        default_kwargs.update(kwargs)
        self.sbd.enable_sbd.assert_called_once_with(
            default_watchdog, watchdog_dict, sbd_options, **default_kwargs
        )

    def call_cmd(self, argv, modifiers=None):
        stonith.sbd_enable(self.lib, argv, _dict_to_modifiers(modifiers or {}))

    def test_no_args(self):
        self.call_cmd([])
        self.assert_called_with(None, dict(), dict())

    def test_watchdog(self):
        self.call_cmd(["watchdog=/dev/wd"])
        self.assert_called_with("/dev/wd", dict(), dict())

    def test_device(self):
        self.call_cmd(["device=/dev/sda"])
        self.assert_called_with(
            None, dict(), dict(), default_device_list=["/dev/sda"]
        )

    def test_options(self):
        self.call_cmd(["SBD_A=a", "SBD_B=b"])
        self.assert_called_with(None, dict(), dict(SBD_A="a", SBD_B="b"))

    def test_multiple_watchdogs_devices(self):
        self.call_cmd(
            [
                "watchdog=/dev/wd",
                "watchdog=/dev/wda@node-a",
                "watchdog=/dev/wdb@node-b",
                "device=/dev/sda1",
                "device=/dev/sda2",
                "device=/dev/sdb1@node-b",
                "device=/dev/sdb2@node-b",
                "device=/dev/sdc1@node-c",
                "device=/dev/sdc2@node-c",
            ]
        )
        self.assert_called_with(
            "/dev/wd",
            {"node-a": "/dev/wda", "node-b": "/dev/wdb"},
            dict(),
            default_device_list=["/dev/sda1", "/dev/sda2"],
            node_device_dict={
                "node-b": ["/dev/sdb1", "/dev/sdb2"],
                "node-c": ["/dev/sdc1", "/dev/sdc2"],
            },
        )

    def test_modifiers(self):
        self.call_cmd(
            [],
            modifiers={
                "force": "",
                "skip-offline": "",
                "no-watchdog-validation": "",
            },
        )
        self.assert_called_with(
            None,
            dict(),
            dict(),
            allow_unknown_opts=True,
            ignore_offline_nodes=True,
            no_watchdog_validation=True,
        )


class SbdDeviceSetup(TestCase):
    def setUp(self):
        self.lib = mock.Mock(spec_set=["sbd"])
        self.sbd = mock.Mock(spec_set=["initialize_block_devices"])
        self.lib.sbd = self.sbd

    def assert_called_with(self, device_list, option_dict):
        self.sbd.initialize_block_devices.assert_called_once_with(
            device_list, option_dict
        )

    def call_cmd(self, argv, modifiers=None):
        all_modifiers = dict(
            force=True,  # otherwise it asks interactively for confirmation
        )
        all_modifiers.update(modifiers or {})
        stonith.sbd_setup_block_device(
            self.lib, argv, _dict_to_modifiers(all_modifiers)
        )

    def test_no_args(self):
        with self.assertRaises(CmdLineInputError) as cm:
            self.call_cmd([])
        self.assertEqual(cm.exception.message, "No device defined")

    @mock.patch("pcs.cli.reports.output.warn")
    def test_minimal(self, mock_warn):
        self.call_cmd(["device=/dev/sda"])
        self.assert_called_with(["/dev/sda"], dict())
        mock_warn.assert_called_once_with(
            "All current content on device(s) '/dev/sda' will be overwritten"
        )

    @mock.patch("pcs.cli.reports.output.warn")
    def test_devices_and_options(self, mock_warn):
        self.call_cmd(["device=/dev/sda", "a=A", "device=/dev/sdb", "b=B"])
        self.assert_called_with(["/dev/sda", "/dev/sdb"], {"a": "A", "b": "B"})
        mock_warn.assert_called_once_with(
            "All current content on device(s) '/dev/sda', '/dev/sdb' will be "
            "overwritten"
        )

    def test_options(self):
        with self.assertRaises(CmdLineInputError) as cm:
            self.call_cmd(["a=A"])
        self.assertEqual(cm.exception.message, "No device defined")


class StonithUpdateScsiDevices(TestCase):
    # pylint: disable=too-many-public-methods
    def setUp(self):
        self.lib = mock.Mock(spec_set=["stonith"])
        self.stonith = mock.Mock(
            spec_set=["update_scsi_devices", "update_scsi_devices_add_remove"]
        )
        self.lib.stonith = self.stonith

    def assert_called_with(self, stonith_id, set_devices, force_flags):
        self.stonith.update_scsi_devices.assert_called_once_with(
            stonith_id, set_devices, force_flags=force_flags
        )
        self.stonith.update_scsi_devices_add_remove.assert_not_called()

    def assert_add_remove_called_with(
        self, stonith_id, add_devices, remove_devices, force_flags
    ):
        self.stonith.update_scsi_devices_add_remove.assert_called_once_with(
            stonith_id, add_devices, remove_devices, force_flags=force_flags
        )
        self.stonith.update_scsi_devices.assert_not_called()

    def assert_bad_syntax_cli_exception(self, args):
        with self.assertRaises(CmdLineInputError) as cm:
            self.call_cmd(args)
        self.assertEqual(cm.exception.message, None)
        self.assertEqual(
            cm.exception.hint,
            (
                "You must specify either list of set devices or at least one "
                "device for add or delete/remove devices"
            ),
        )
        self.stonith.update_scsi_devices.assert_not_called()
        self.stonith.update_scsi_devices_add_remove.assert_not_called()

    def call_cmd(self, argv, modifiers=None):
        stonith.stonith_update_scsi_devices(
            self.lib, argv, dict_to_modifiers(modifiers or {})
        )

    def test_no_args(self):
        with self.assertRaises(CmdLineInputError) as cm:
            self.call_cmd([])
        self.assertEqual(cm.exception.message, None)

    def test_only_stonith_id(self):
        with self.assertRaises(CmdLineInputError) as cm:
            self.call_cmd(["stonith-id"])
        self.assertEqual(cm.exception.message, None)

    def test_unknown_keyword(self):
        with self.assertRaises(CmdLineInputError) as cm:
            self.call_cmd(["stonith-id", "unset"])
        self.assertEqual(cm.exception.message, None)

    def test_supported_options(self):
        self.call_cmd(
            ["stonith-id", "set", "d1", "d2"],
            {"skip-offline": True, "request-timeout": 60},
        )
        self.assert_called_with(
            "stonith-id",
            ["d1", "d2"],
            [reports.codes.SKIP_OFFLINE_NODES],
        )

    def test_unsupported_options(self):
        with self.assertRaises(CmdLineInputError) as cm:
            self.call_cmd(["stonith-id", "set", "d1", "d2"], {"force": True})
        self.assertEqual(
            cm.exception.message,
            "Specified option '--force' is not supported in this command",
        )

    def test_only_set_keyword(self):
        self.assert_bad_syntax_cli_exception(["stonith-id", "set"])

    def test_only_add_keyword(self):
        self.assert_bad_syntax_cli_exception(["stonith-id", "add"])

    def test_only_remove_keyword(self):
        self.assert_bad_syntax_cli_exception(["stonith-id", "remove"])

    def test_only_delete_keyword(self):
        self.assert_bad_syntax_cli_exception(["stonith-id", "delete"])

    def test_add_and_empty_remove(self):
        self.assert_bad_syntax_cli_exception(
            ["stonith-id", "add", "d1", "remove"]
        )

    def test_add_and_empty_delete(self):
        self.assert_bad_syntax_cli_exception(
            ["stonith-id", "add", "d1", "delete"]
        )

    def test_empty_add_and_remove(self):
        self.assert_bad_syntax_cli_exception(
            ["stonith-id", "add", "remove", "d1"]
        )

    def test_empty_add_and_delete(self):
        self.assert_bad_syntax_cli_exception(
            ["stonith-id", "add", "delete", "d1"]
        )

    def test_empty_remove_and_delete(self):
        self.assert_bad_syntax_cli_exception(
            ["stonith-id", "remove", "delete", "d1"]
        )

    def test_empty_delete_and_remove(self):
        self.assert_bad_syntax_cli_exception(
            ["stonith-id", "delete", "remove", "d1"]
        )

    def test_empty_add_empty_remove_empty_delete(self):
        self.assert_bad_syntax_cli_exception(
            ["stonith-id", "add", "delete", "remove"]
        )

    def test_set_add_remove_delete_devices(self):
        self.assert_bad_syntax_cli_exception(
            [
                "stonith-id",
                "set",
                "add",
                "d2",
                "remove",
                "d3",
                "delete",
                "d4",
            ]
        )

    def test_set_devices(self):
        self.call_cmd(["stonith-id", "set", "d1", "d2"])
        self.assert_called_with("stonith-id", ["d1", "d2"], [])

    def test_add_devices(self):
        self.call_cmd(["stonith-id", "add", "d1", "d2"])
        self.assert_add_remove_called_with("stonith-id", ["d1", "d2"], [], [])

    def test_remove_devices(self):
        self.call_cmd(["stonith-id", "remove", "d1", "d2"])
        self.assert_add_remove_called_with("stonith-id", [], ["d1", "d2"], [])

    def test_delete_devices(self):
        self.call_cmd(["stonith-id", "delete", "d1", "d2"])
        self.assert_add_remove_called_with("stonith-id", [], ["d1", "d2"], [])

    def test_add_remove_devices(self):
        self.call_cmd(["stonith-id", "add", "d1", "d2", "remove", "d3", "d4"])
        self.assert_add_remove_called_with(
            "stonith-id", ["d1", "d2"], ["d3", "d4"], []
        )

    def test_add_delete_devices(self):
        self.call_cmd(["stonith-id", "add", "d1", "d2", "delete", "d3", "d4"])
        self.assert_add_remove_called_with(
            "stonith-id", ["d1", "d2"], ["d3", "d4"], []
        )

    def test_add_delete_remove_devices(self):
        self.call_cmd(
            [
                "stonith-id",
                "add",
                "d1",
                "d2",
                "delete",
                "d3",
                "d4",
                "remove",
                "d5",
            ]
        )
        self.assert_add_remove_called_with(
            "stonith-id", ["d1", "d2"], ["d3", "d4", "d5"], []
        )

    def test_remove_delete_devices(self):
        self.call_cmd(
            ["stonith-id", "remove", "d2", "d1", "delete", "d4", "d3"]
        )
        self.assert_add_remove_called_with(
            "stonith-id", [], ["d4", "d3", "d2", "d1"], []
        )
