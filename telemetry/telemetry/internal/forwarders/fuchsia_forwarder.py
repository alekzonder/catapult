# Copyright 2019 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import tempfile

from telemetry.core import util
from telemetry.internal import forwarders
from telemetry.internal.forwarders import forwarder_utils


class FuchsiaForwarderFactory(forwarders.ForwarderFactory):

  def __init__(self, command_runner):
    super(FuchsiaForwarderFactory, self).__init__()
    self._command_runner = command_runner

  def Create(self, local_port, remote_port, reverse=False):
    return FuchsiaSshForwarder(local_port, remote_port,
                               self._command_runner,
                               port_forward=not reverse)


class FuchsiaSshForwarder(forwarders.Forwarder):

  def __init__(self, local_port, remote_port, command_runner, port_forward):
    """Sets up ssh port forwarding betweeen a Fuchsia device and the host.

    Args:
      local_port: Port on the host.
      remote_port: Port on the Fuchsia device.
      command_runner: Contains information related to ssh configuration.
      port_forward: Determines the direction of the connection."""
    super(FuchsiaSshForwarder, self).__init__()
    self._proc = None

    if port_forward:
      assert local_port, 'Local port must be given'
    else:
      assert remote_port, 'Remote port must be given'
      if not local_port:
        # Choose an available port on the host.
        local_port = util.GetUnreservedAvailableLocalPort()

    forward_cmd = [
        '-O', 'forward',  # Send SSH mux control signal.
        '-N',  # Don't execute command
        '-T'  # Don't allocate terminal.
    ]

    forward_cmd.append(forwarder_utils.GetForwardingArgs(
        local_port, remote_port, self.host_ip, port_forward))

    with tempfile.NamedTemporaryFile() as stderr_file:
      self._proc = command_runner.RunCommandPiped(forward_cmd,
                                                  stderr=stderr_file)
      if not remote_port:
        remote_port = forwarder_utils.ReadRemotePort(stderr_file.name)

    self._StartedForwarding(local_port, remote_port)

  def Close(self):
    if self._proc:
      self._proc.kill()
      self._proc = None
    super(FuchsiaSshForwarder, self).Close()
