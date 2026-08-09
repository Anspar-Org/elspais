# Verifies: REQ-o00074-N
"""The disclosure owed when a client's use does not bind the daemon.

A client whose handle cannot be derived uses a daemon that does not know
it exists: the daemon will stop when its recorded clients go, whatever
this client is doing. REQ-o00074-N obliges the tool to say so, and to
name what the client can supply -- which is what makes the declarative
handle discoverable to a harness author who has never heard of it. The
same assertion bounds the noise: the disclosure does not repeat for every
use, so it is recorded per daemon rather than per command.
"""

from __future__ import annotations

from elspais.mcp.daemon import _daemon_dir, notify_unbound_lifetime


class TestUnboundLifetimeIsDisclosed:
    def test_REQ_o00074_N_the_notice_names_the_remedy(self, tmp_path, capsys):
        """Validates REQ-o00074-N: the disclosure says the lifetime is not
        bound to this client and names what it can supply to bind it. A
        report of a condition without its remedy sends the reader nowhere."""
        assert notify_unbound_lifetime(tmp_path, "no client handle could be derived") is True
        err = capsys.readouterr().err
        assert "ELSPAIS_CLIENT_PID" in err
        assert "idle timeout" in err

    def test_REQ_o00074_N_the_notice_does_not_repeat(self, tmp_path, capsys):
        """Validates REQ-o00074-N: the disclosure does not repeat for every
        use. A warning on every command is one readers learn to ignore."""
        assert notify_unbound_lifetime(tmp_path, "no client handle could be derived") is True
        capsys.readouterr()
        assert notify_unbound_lifetime(tmp_path, "no client handle could be derived") is False
        assert capsys.readouterr().err == ""

    def test_REQ_o00074_N_fresh_daemon_discloses_again(self, tmp_path, capsys):
        """Validates REQ-o00074-N: the disclosure is scoped to the daemon it
        describes, so a client meeting a different daemon is told about that
        one rather than silenced by what it was told about the last."""
        notify_unbound_lifetime(tmp_path, "no client handle could be derived")
        capsys.readouterr()
        (_daemon_dir(tmp_path) / "daemon.client-notice").unlink()
        assert notify_unbound_lifetime(tmp_path, "no client handle could be derived") is True

    def test_REQ_o00074_N_an_unusable_declaration_is_reported(self, tmp_path, capsys):
        """Validates REQ-o00074-N: a declaration that could not be used is
        disclosed as such. A caller that set the variable and was ignored
        needs to know it was ignored, not that nothing was declared."""
        notify_unbound_lifetime(tmp_path, "the declared client handle could not be used")
        assert "could not be used" in capsys.readouterr().err
