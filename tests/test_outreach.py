"""Tests for the outreach module: email_sender, linkedin_queue, sequence_manager."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from amida_agent.models import (
    ActivityLog,
    Channel,
    OutreachDraft,
    PEFirm,
    Prospect,
    ProspectStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with fresh tables for each test."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def pe_firm(db_session):
    firm = PEFirm(name="Nordic Capital", website="https://nordiccapital.com", country="Sweden")
    db_session.add(firm)
    db_session.commit()
    db_session.refresh(firm)
    return firm


@pytest.fixture
def prospect(db_session, pe_firm):
    p = Prospect(
        pe_firm_id=pe_firm.id,
        first_name="Erik",
        last_name="Lindqvist",
        full_name="Erik Lindqvist",
        title="Head of AI",
        email="erik@example.com",
        linkedin_url="https://linkedin.com/in/eriklindqvist",
        dossier="# Erik Lindqvist\n## Head of AI at Nordic Capital\nExperienced AI leader...",
        status=ProspectStatus.approved,
        relevance_score=0.85,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def approved_draft(db_session, prospect):
    draft = OutreachDraft(
        prospect_id=prospect.id,
        channel=Channel.email,
        sequence_step=1,
        subject="AI transformation at Nordic Capital",
        body="Hi Erik, I noticed your recent move to Nordic Capital...",
        approved=True,
        approved_at=datetime.utcnow(),
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)
    return draft


def _mock_get_session(session):
    """Create a context-manager mock that yields the given session."""
    from contextlib import contextmanager

    @contextmanager
    def _get_session():
        yield session

    return _get_session


# ---------------------------------------------------------------------------
# email_sender tests
# ---------------------------------------------------------------------------

class TestSmartleadRequest:
    @patch("amida_agent.outreach.email_sender.httpx.request")
    @patch("amida_agent.outreach.email_sender.time.sleep")
    def test_injects_api_key(self, mock_sleep, mock_request):
        from amida_agent.outreach.email_sender import _smartlead_request

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}
        mock_request.return_value = mock_resp

        with patch("amida_agent.outreach.email_sender.settings") as mock_settings:
            mock_settings.smartlead_api_key = "test-key-123"
            result = _smartlead_request("GET", "/test")

        call_kwargs = mock_request.call_args
        assert call_kwargs[1]["params"]["api_key"] == "test-key-123"
        assert result == {"ok": True}

    @patch("amida_agent.outreach.email_sender.httpx.request")
    @patch("amida_agent.outreach.email_sender.time.sleep")
    def test_retries_on_429(self, mock_sleep, mock_request):
        from amida_agent.outreach.email_sender import _smartlead_request

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}
        mock_request.side_effect = [resp_429, resp_200]

        with patch("amida_agent.outreach.email_sender.settings") as mock_settings:
            mock_settings.smartlead_api_key = "key"
            result = _smartlead_request("GET", "/test")

        assert result == {"ok": True}
        assert mock_request.call_count == 2

    @patch("amida_agent.outreach.email_sender.httpx.request")
    @patch("amida_agent.outreach.email_sender.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep, mock_request):
        from amida_agent.outreach.email_sender import _smartlead_request

        resp_429 = MagicMock()
        resp_429.status_code = 429
        mock_request.return_value = resp_429

        with patch("amida_agent.outreach.email_sender.settings") as mock_settings:
            mock_settings.smartlead_api_key = "key"
            with pytest.raises(RuntimeError, match="rate limited"):
                _smartlead_request("GET", "/test")


class TestSendApprovedDraft:
    def test_skips_without_api_key(self, db_session, approved_draft):
        from amida_agent.outreach.email_sender import send_approved_draft

        with patch("amida_agent.outreach.email_sender.settings") as mock_settings:
            mock_settings.smartlead_api_key = ""
            send_approved_draft(approved_draft.id)

        # Draft should be unchanged
        db_session.refresh(approved_draft)
        assert approved_draft.smartlead_campaign_id is None

    @patch("amida_agent.outreach.email_sender.add_lead_to_campaign")
    @patch("amida_agent.outreach.email_sender.add_sequence_step")
    @patch("amida_agent.outreach.email_sender.create_campaign")
    def test_sends_and_updates_status(
        self, mock_create, mock_add_step, mock_add_lead, db_session, prospect, approved_draft
    ):
        from amida_agent.outreach.email_sender import send_approved_draft

        mock_create.return_value = "camp-123"
        mock_add_lead.return_value = "lead-456"

        with (
            patch("amida_agent.outreach.email_sender.settings") as mock_settings,
            patch("amida_agent.outreach.email_sender.get_session", _mock_get_session(db_session)),
            patch("amida_agent.notifications.notifier.notify"),
        ):
            mock_settings.smartlead_api_key = "test-key"
            mock_settings.smartlead_sending_account = ""
            mock_settings.step_delays = [3, 5, 7]
            send_approved_draft(approved_draft.id)

        db_session.refresh(approved_draft)
        db_session.refresh(prospect)

        assert approved_draft.smartlead_campaign_id == "camp-123"
        assert approved_draft.smartlead_lead_id == "lead-456"
        assert prospect.status == ProspectStatus.sent

        # Should have logged an activity
        log = db_session.exec(
            select(ActivityLog).where(ActivityLog.action == "email_sent")
        ).first()
        assert log is not None
        assert log.prospect_id == prospect.id

    @patch("amida_agent.outreach.email_sender.add_lead_to_campaign")
    @patch("amida_agent.outreach.email_sender.add_sequence_step")
    @patch("amida_agent.outreach.email_sender.create_campaign")
    def test_uses_edited_body_when_present(
        self, mock_create, mock_add_step, mock_add_lead, db_session, prospect, approved_draft
    ):
        from amida_agent.outreach.email_sender import send_approved_draft

        approved_draft.edited_body = "Edited version of the email."
        db_session.commit()

        mock_create.return_value = "camp-1"
        mock_add_lead.return_value = "lead-1"

        with (
            patch("amida_agent.outreach.email_sender.settings") as mock_settings,
            patch("amida_agent.outreach.email_sender.get_session", _mock_get_session(db_session)),
            patch("amida_agent.notifications.notifier.notify"),
        ):
            mock_settings.smartlead_api_key = "key"
            mock_settings.smartlead_sending_account = ""
            mock_settings.step_delays = [3, 5, 7]
            send_approved_draft(approved_draft.id)

        # add_sequence_step should have been called with the edited body
        call_args = mock_add_step.call_args
        assert call_args[0][3] == "Edited version of the email."

    def test_skips_non_email_channel(self, db_session, prospect):
        from amida_agent.outreach.email_sender import send_approved_draft

        linkedin_draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=Channel.linkedin,
            sequence_step=1,
            subject="Connection",
            body="Hey!",
            approved=True,
            approved_at=datetime.utcnow(),
        )
        db_session.add(linkedin_draft)
        db_session.commit()
        db_session.refresh(linkedin_draft)

        with (
            patch("amida_agent.outreach.email_sender.settings") as mock_settings,
            patch("amida_agent.outreach.email_sender.get_session", _mock_get_session(db_session)),
        ):
            mock_settings.smartlead_api_key = "key"
            send_approved_draft(linkedin_draft.id)

        # Should not have set any Smartlead IDs
        db_session.refresh(linkedin_draft)
        assert linkedin_draft.smartlead_campaign_id is None

    def test_skips_prospect_without_email(self, db_session, pe_firm):
        from amida_agent.outreach.email_sender import send_approved_draft

        no_email_prospect = Prospect(
            pe_firm_id=pe_firm.id,
            first_name="No",
            last_name="Email",
            full_name="No Email",
            title="CTO",
            email=None,
            status=ProspectStatus.approved,
        )
        db_session.add(no_email_prospect)
        db_session.commit()
        db_session.refresh(no_email_prospect)

        draft = OutreachDraft(
            prospect_id=no_email_prospect.id,
            channel=Channel.email,
            sequence_step=1,
            subject="Test",
            body="Test body",
            approved=True,
            approved_at=datetime.utcnow(),
        )
        db_session.add(draft)
        db_session.commit()
        db_session.refresh(draft)

        with (
            patch("amida_agent.outreach.email_sender.settings") as mock_settings,
            patch("amida_agent.outreach.email_sender.get_session", _mock_get_session(db_session)),
        ):
            mock_settings.smartlead_api_key = "key"
            send_approved_draft(draft.id)

        db_session.refresh(draft)
        assert draft.smartlead_campaign_id is None


class TestFetchStatus:
    @patch("amida_agent.outreach.email_sender._smartlead_request")
    def test_fetch_lead_status(self, mock_req):
        from amida_agent.outreach.email_sender import fetch_lead_status

        mock_req.return_value = {"replied": True, "opened": 3}

        with patch("amida_agent.outreach.email_sender.settings") as mock_settings:
            mock_settings.smartlead_api_key = "key"
            result = fetch_lead_status("camp-1", "lead-1")

        assert result["replied"] is True

    def test_fetch_lead_status_no_key(self):
        from amida_agent.outreach.email_sender import fetch_lead_status

        with patch("amida_agent.outreach.email_sender.settings") as mock_settings:
            mock_settings.smartlead_api_key = ""
            result = fetch_lead_status("camp-1", "lead-1")

        assert result == {}


# ---------------------------------------------------------------------------
# linkedin_queue tests
# ---------------------------------------------------------------------------

class TestLinkedInQueue:
    def test_queue_connection_request(self, db_session, prospect):
        from amida_agent.outreach.linkedin_queue import queue_connection_request

        with (
            patch("amida_agent.outreach.linkedin_queue.get_session", _mock_get_session(db_session)),
            patch("amida_agent.config.settings") as mock_settings,
            patch("amida_agent.ai.composer.generate", return_value="Hi Erik, love your AI work!"),
        ):
            mock_settings.anthropic_api_key = "test-key"
            draft_id = queue_connection_request(prospect.id)

        assert draft_id is not None
        draft = db_session.get(OutreachDraft, draft_id)
        assert draft.channel == Channel.linkedin
        assert draft.sequence_step == 1
        assert len(draft.body) > 0
        assert draft.approved is None  # pending

        log = db_session.exec(
            select(ActivityLog).where(ActivityLog.action == "linkedin_connection_queued")
        ).first()
        assert log is not None

    def test_queue_connection_request_no_api_key(self, db_session, prospect):
        from amida_agent.outreach.linkedin_queue import queue_connection_request

        with (
            patch("amida_agent.outreach.linkedin_queue.get_session", _mock_get_session(db_session)),
            patch("amida_agent.config.settings") as mock_settings,
        ):
            mock_settings.anthropic_api_key = ""
            draft_id = queue_connection_request(prospect.id)

        assert draft_id is None

    def test_queue_linkedin_message(self, db_session, prospect):
        from amida_agent.outreach.linkedin_queue import queue_linkedin_message

        with (
            patch("amida_agent.outreach.linkedin_queue.get_session", _mock_get_session(db_session)),
            patch("amida_agent.config.settings") as mock_settings,
            patch("amida_agent.ai.composer.generate", return_value="Thanks for connecting, Erik!"),
        ):
            mock_settings.anthropic_api_key = "test-key"
            draft_id = queue_linkedin_message(prospect.id)

        assert draft_id is not None
        draft = db_session.get(OutreachDraft, draft_id)
        assert draft.channel == Channel.linkedin
        assert draft.sequence_step == 2

    def test_get_pending_linkedin_actions(self, db_session, prospect):
        from amida_agent.outreach.linkedin_queue import get_pending_linkedin_actions

        # Create an approved LinkedIn draft
        draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=Channel.linkedin,
            sequence_step=1,
            subject="Connection Request",
            body="Hi Erik!",
            approved=True,
            approved_at=datetime.utcnow(),
        )
        db_session.add(draft)
        db_session.commit()

        with patch("amida_agent.outreach.linkedin_queue.get_session", _mock_get_session(db_session)):
            actions = get_pending_linkedin_actions()

        assert len(actions) == 1
        assert actions[0]["prospect_name"] == "Erik Lindqvist"
        assert actions[0]["action_type"] == "connection_request"
        assert actions[0]["message"] == "Hi Erik!"

    def test_get_pending_excludes_sent(self, db_session, prospect):
        from amida_agent.outreach.linkedin_queue import get_pending_linkedin_actions

        draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=Channel.linkedin,
            sequence_step=1,
            subject="Connection",
            body="Hi!",
            approved=True,
            approved_at=datetime.utcnow(),
            smartlead_lead_id="manual",  # already marked sent
        )
        db_session.add(draft)
        db_session.commit()

        with patch("amida_agent.outreach.linkedin_queue.get_session", _mock_get_session(db_session)):
            actions = get_pending_linkedin_actions()

        assert len(actions) == 0

    def test_mark_linkedin_sent(self, db_session, prospect):
        from amida_agent.outreach.linkedin_queue import mark_linkedin_sent

        draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=Channel.linkedin,
            sequence_step=1,
            subject="Connection",
            body="Hi!",
            approved=True,
            approved_at=datetime.utcnow(),
        )
        db_session.add(draft)
        db_session.commit()
        db_session.refresh(draft)

        with patch("amida_agent.outreach.linkedin_queue.get_session", _mock_get_session(db_session)):
            result = mark_linkedin_sent(draft.id)

        assert result is True
        db_session.refresh(draft)
        assert draft.smartlead_lead_id == "manual"

        db_session.refresh(prospect)
        assert prospect.status == ProspectStatus.sent

        log = db_session.exec(
            select(ActivityLog).where(ActivityLog.action == "linkedin_connection_sent")
        ).first()
        assert log is not None

    def test_mark_linkedin_sent_wrong_channel(self, db_session, prospect):
        from amida_agent.outreach.linkedin_queue import mark_linkedin_sent

        email_draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=Channel.email,
            sequence_step=1,
            subject="Email",
            body="Hi!",
            approved=True,
        )
        db_session.add(email_draft)
        db_session.commit()
        db_session.refresh(email_draft)

        with patch("amida_agent.outreach.linkedin_queue.get_session", _mock_get_session(db_session)):
            result = mark_linkedin_sent(email_draft.id)

        assert result is False


# ---------------------------------------------------------------------------
# sequence_manager tests
# ---------------------------------------------------------------------------

class TestSequenceManager:
    def test_get_sequence_status(self, db_session, prospect, approved_draft):
        from amida_agent.outreach.sequence_manager import get_sequence_status

        prospect.status = ProspectStatus.sent
        db_session.commit()

        with patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)):
            status = get_sequence_status(prospect.id)

        assert status["current_step"] == 1
        assert status["max_steps"] == 4
        assert status["has_reply"] is False
        assert status["status"] == "sent"

    def test_get_sequence_status_no_prospect(self, db_session):
        from amida_agent.outreach.sequence_manager import get_sequence_status

        with patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)):
            status = get_sequence_status(9999)

        assert status == {}

    def test_handle_reply(self, db_session, prospect):
        from amida_agent.outreach.sequence_manager import handle_reply

        prospect.status = ProspectStatus.sent
        db_session.commit()

        with patch("amida_agent.notifications.notifier.notify_reply"):
            handle_reply(prospect.id, session=db_session)

        db_session.commit()
        db_session.refresh(prospect)
        assert prospect.status == ProspectStatus.replied

        log = db_session.exec(
            select(ActivityLog).where(ActivityLog.action == "reply_received")
        ).first()
        assert log is not None

    def test_check_sequence_skips_max_step(self, db_session, prospect, approved_draft):
        """Prospect at step 4 should be skipped."""
        from amida_agent.outreach.sequence_manager import check_sequence_progression

        prospect.status = ProspectStatus.sent
        approved_draft.sequence_step = 4
        approved_draft.approved_at = datetime.utcnow() - timedelta(days=10)
        db_session.commit()

        with (
            patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)),
            patch("amida_agent.outreach.sequence_manager.settings") as mock_settings,
        ):
            mock_settings.step_delays = [3, 5, 7]
            mock_settings.anthropic_api_key = "key"
            mock_settings.auto_approve_followups = False
            result = check_sequence_progression()

        assert result["composed"] == 0
        assert result["skipped"] == 1

    def test_check_sequence_skips_if_delay_not_elapsed(self, db_session, prospect, approved_draft):
        """Should not compose if delay hasn't elapsed."""
        from amida_agent.outreach.sequence_manager import check_sequence_progression

        prospect.status = ProspectStatus.sent
        approved_draft.approved_at = datetime.utcnow() - timedelta(days=1)  # only 1 day ago
        db_session.commit()

        with (
            patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)),
            patch("amida_agent.outreach.sequence_manager.settings") as mock_settings,
        ):
            mock_settings.step_delays = [3, 5, 7]
            mock_settings.anthropic_api_key = "key"
            mock_settings.auto_approve_followups = False
            result = check_sequence_progression()

        assert result["composed"] == 0

    def test_check_sequence_composes_next_step(self, db_session, prospect, approved_draft):
        """Should compose step 2 after 3+ days with no reply."""
        from amida_agent.outreach.sequence_manager import check_sequence_progression

        prospect.status = ProspectStatus.sent
        approved_draft.approved_at = datetime.utcnow() - timedelta(days=4)
        db_session.commit()

        with (
            patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)),
            patch("amida_agent.outreach.sequence_manager.settings") as mock_settings,
            patch("amida_agent.ai.composer.compose_email") as mock_compose,
            patch("amida_agent.outreach.email_sender.fetch_lead_status", return_value={}),
            patch("amida_agent.notifications.notifier.notify_needs_approval"),
        ):
            mock_settings.step_delays = [3, 5, 7]
            mock_settings.anthropic_api_key = "key"
            mock_settings.auto_approve_followups = False
            mock_compose.return_value = ("Follow up subject", "Follow up body")
            result = check_sequence_progression()

        assert result["composed"] == 1

        # Should have created a new draft at step 2
        step2 = db_session.exec(
            select(OutreachDraft)
            .where(OutreachDraft.prospect_id == prospect.id)
            .where(OutreachDraft.sequence_step == 2)
        ).first()
        assert step2 is not None
        assert step2.subject == "Follow up subject"
        assert step2.approved is None  # pending approval

    def test_check_sequence_auto_approves_when_configured(self, db_session, prospect, approved_draft):
        from amida_agent.outreach.sequence_manager import check_sequence_progression

        prospect.status = ProspectStatus.sent
        approved_draft.approved_at = datetime.utcnow() - timedelta(days=4)
        db_session.commit()

        with (
            patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)),
            patch("amida_agent.outreach.sequence_manager.settings") as mock_settings,
            patch("amida_agent.ai.composer.compose_email") as mock_compose,
            patch("amida_agent.outreach.email_sender.fetch_lead_status", return_value={}),
        ):
            mock_settings.step_delays = [3, 5, 7]
            mock_settings.anthropic_api_key = "key"
            mock_settings.auto_approve_followups = True
            mock_compose.return_value = ("Subject", "Body")
            result = check_sequence_progression()

        step2 = db_session.exec(
            select(OutreachDraft)
            .where(OutreachDraft.prospect_id == prospect.id)
            .where(OutreachDraft.sequence_step == 2)
        ).first()
        assert step2.approved is True

    def test_check_sequence_detects_reply(self, db_session, prospect, approved_draft):
        """Should mark prospect as replied when Smartlead reports a reply."""
        from amida_agent.outreach.sequence_manager import check_sequence_progression

        prospect.status = ProspectStatus.sent
        approved_draft.approved_at = datetime.utcnow() - timedelta(days=4)
        approved_draft.smartlead_campaign_id = "camp-1"
        approved_draft.smartlead_lead_id = "lead-1"
        db_session.commit()

        with (
            patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)),
            patch("amida_agent.outreach.sequence_manager.settings") as mock_settings,
            patch("amida_agent.outreach.email_sender.fetch_lead_status") as mock_fetch,
            patch("amida_agent.notifications.notifier.notify_reply"),
        ):
            mock_settings.step_delays = [3, 5, 7]
            mock_settings.anthropic_api_key = "key"
            mock_settings.auto_approve_followups = False
            mock_fetch.return_value = {"replied": True, "reply_count": 1}
            result = check_sequence_progression()

        assert result["replied"] == 1
        assert result["composed"] == 0

        db_session.refresh(prospect)
        assert prospect.status == ProspectStatus.replied


class TestSyncSmartlead:
    def test_sync_no_api_key(self):
        from amida_agent.outreach.sequence_manager import sync_smartlead_statuses

        with patch("amida_agent.outreach.sequence_manager.settings") as mock_settings:
            mock_settings.smartlead_api_key = ""
            result = sync_smartlead_statuses()

        assert result == {"synced": 0, "replies": 0}

    def test_sync_detects_reply(self, db_session, prospect, approved_draft):
        from amida_agent.outreach.sequence_manager import sync_smartlead_statuses

        prospect.status = ProspectStatus.sent
        approved_draft.smartlead_campaign_id = "camp-1"
        approved_draft.smartlead_lead_id = "lead-1"
        db_session.commit()

        with (
            patch("amida_agent.outreach.sequence_manager.get_session", _mock_get_session(db_session)),
            patch("amida_agent.outreach.sequence_manager.settings") as mock_settings,
            patch("amida_agent.outreach.email_sender.fetch_lead_status") as mock_fetch,
            patch("amida_agent.notifications.notifier.notify_reply"),
        ):
            mock_settings.smartlead_api_key = "key"
            mock_fetch.return_value = {"is_replied": True}
            result = sync_smartlead_statuses()

        assert result["synced"] == 1
        assert result["replies"] == 1

        db_session.refresh(prospect)
        assert prospect.status == ProspectStatus.replied


class TestHasReply:
    def test_replied_field(self):
        from amida_agent.outreach.sequence_manager import _has_reply

        assert _has_reply({"replied": True}) is True
        assert _has_reply({"replied": False}) is False

    def test_reply_count_field(self):
        from amida_agent.outreach.sequence_manager import _has_reply

        assert _has_reply({"reply_count": 2}) is True
        assert _has_reply({"reply_count": 0}) is False

    def test_is_replied_field(self):
        from amida_agent.outreach.sequence_manager import _has_reply

        assert _has_reply({"is_replied": True}) is True

    def test_empty_status(self):
        from amida_agent.outreach.sequence_manager import _has_reply

        assert _has_reply({}) is False
        assert _has_reply(None) is False


class TestStepDelaysProperty:
    def test_default_delays(self):
        from amida_agent.config import Settings

        s = Settings(sequence_step_delays="3,5,7")
        assert s.step_delays == [3, 5, 7]

    def test_custom_delays(self):
        from amida_agent.config import Settings

        s = Settings(sequence_step_delays="2, 4, 6")
        assert s.step_delays == [2, 4, 6]

    def test_invalid_delays_fallback(self):
        from amida_agent.config import Settings

        s = Settings(sequence_step_delays="invalid")
        assert s.step_delays == [3, 5, 7]
