"""Tests for `vadgr run`: what it sends, what it watches, what it exits."""

from unittest import mock

from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, *args, follow_returns=None, post_returns=None):
    from cli.main import run

    post = mock.Mock(return_value=post_returns or {"id": "run-999", "status": "queued"})
    follow = mock.Mock(return_value=follow_returns)
    with mock.patch("cli.client.api_post", post), \
         mock.patch("cli.stream.follow_run", follow):
        result = runner.invoke(run, list(args), obj={"api_url": "http://x"})
    return result, post, follow


class TestWhatItSends:
    def test_sends_the_sentence_as_the_task(self, runner):
        result, post, _ = _invoke(runner, "Summarise my mail", "--background")
        assert result.exit_code == 0
        assert post.call_args.args[1] == "/api/runs"
        assert post.call_args.args[2] == {"task": "Summarise my mail"}

    def test_sends_a_named_provider_and_model_together(self, runner):
        _, post, _ = _invoke(
            runner, "do a thing", "--background", "-p", "codex", "-m", "gpt-5.4",
        )
        assert post.call_args.args[2] == {
            "task": "do a thing", "provider": "codex", "model": "gpt-5.4",
        }

    def test_a_provider_without_a_model_never_reaches_the_daemon(self, runner):
        result, post, _ = _invoke(runner, "do a thing", "-p", "codex")
        assert result.exit_code == 2
        post.assert_not_called()

    def test_an_empty_sentence_never_reaches_the_daemon(self, runner):
        result, post, _ = _invoke(runner, "   ")
        assert result.exit_code == 2
        post.assert_not_called()


class TestWhatItWatches:
    def test_background_skips_the_stream(self, runner):
        result, _, follow = _invoke(runner, "do a thing", "--background")
        assert result.exit_code == 0
        assert "run-999" in result.output
        follow.assert_not_called()

    def test_foreground_follows_the_run(self, runner):
        from cli import stream

        _, _, follow = _invoke(runner, "do a thing", follow_returns=stream.COMPLETED)
        follow.assert_called_once_with("http://x", "run-999")


class TestExitCodes:
    """The exit code is the run's outcome, and it is what a script branches on."""

    def test_completed_is_zero(self, runner):
        from cli import stream

        result, _, _ = _invoke(runner, "do a thing", follow_returns=stream.COMPLETED)
        assert result.exit_code == 0

    def test_failed_is_one(self, runner):
        from cli import stream

        result, _, _ = _invoke(runner, "do a thing", follow_returns=stream.FAILED)
        assert result.exit_code == 1

    def test_detached_is_130(self, runner):
        from cli import stream

        result, _, _ = _invoke(runner, "do a thing", follow_returns=stream.DETACHED)
        assert result.exit_code == 130


class TestCtrlC:
    def test_detaching_does_not_cancel_the_run(self):
        """Ctrl-C stops watching. It must not kill hours of unattended work."""
        from cli import stream

        def interrupt(coroutine):
            coroutine.close()
            raise KeyboardInterrupt

        with mock.patch("cli.stream.asyncio.run", side_effect=interrupt), \
             mock.patch("cli.client.api_post") as post:
            outcome = stream.follow_run("http://x", "run-999")

        assert outcome == stream.DETACHED
        post.assert_not_called()
