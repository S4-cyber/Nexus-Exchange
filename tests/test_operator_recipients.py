import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from nexus_exchange.operator_drafts import prepare_rfq
from nexus_exchange.operator_recipients import (RecipientStore, prepare_recipient,
    render_correspondence, validate_declaration)
from test_operator_drafts import NOW,request

REFERENCE="sha256:"+"a"*64+";bytes:12"

def draft(**changes):
    return prepare_rfq(dict(request(),supplier_profile_sha256="d"*64,**changes),halted=False)

def contact(**changes):
    return dict(dict(scheme="REGISTRY",identifier="SUPPLIER-1",organization_name="Synthetic supplier",
        email="quotes@example.org",source_url="https://www.example.org/contact",
        observed_at=NOW.isoformat()),**changes)

class RecipientTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"recipients.sqlite3"

    def prepare(self,raw=None,rfq=None,**changes):
        kwargs=dict(organization_name="Synthetic supplier",evidence_reference=REFERENCE,now=NOW,halted=False)
        kwargs.update(changes)
        return prepare_recipient(draft() if rfq is None else rfq,contact() if raw is None else raw,**kwargs)

    def test_exact_role_mailbox_and_nonbinding_preview(self):
        candidate=self.prepare()
        self.assertEqual(candidate,self.prepare())
        self.assertEqual(candidate["scope"]["draft_id"],draft()["draft_id"])
        for key in ("recipient_verified","send_enabled","external_authority","independently_verified",
                    "mailbox_control_verified","source_authenticity_verified","contact_permission_verified"):
            self.assertIs(candidate[key],False)
        text=render_correspondence(draft(),candidate,halted=False)
        self.assertIn("DO NOT SEND",text)
        self.assertIn("quotes@example.org",text)
        self.assertIn("unverified",text)
        self.assertIn("Document indexing",text)
        self.assertNotIn("mailto:",text)

    def test_invalid_contacts_and_domain_confusion(self):
        for changes in (dict(email="person@example.org"),dict(email="quotes@EXAMPLE.org"),
                dict(email="quotes@example.org\nBcc: x@y.org"),dict(email="quotes@127.0.0.1"),
                dict(source_url="https://example.org.evil.test/contact"),
                dict(source_url="https://example.org@evil.test/contact"),
                dict(source_url="http://example.org/contact"),dict(source_url="https://example.org:443/contact"),
                dict(source_url="https://example.org/contact?secret=x"),
                dict(source_url="https://example.org/contact#fragment"),
                dict(source_url="https://example.org\\@evil.test"),dict(source_url="https://example.org/é"),
                dict(identifier="OTHER"),dict(scheme="OTHER"),dict(organization_name="Other company"),
                dict(observed_at=(NOW+timedelta(seconds=1)).isoformat()),
                dict(observed_at=(NOW-timedelta(days=2)).isoformat()),dict(recipient_verified=True)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.prepare(contact(**changes))

    def test_invalid_reference_and_legacy_rfq(self):
        for ref in ("not a hash","sha256:"+"z"*64+";bytes:12","sha256:"+"a"*64+";bytes:0"):
            with self.assertRaises(ValueError):
                self.prepare(evidence_reference=ref)
        with self.assertRaises(ValueError):
            self.prepare(rfq=prepare_rfq(request(),halted=False))

    def test_scope_changes_and_authority_forgery(self):
        candidate=self.prepare()
        changed=draft(region="US-NY")
        self.assertNotEqual(self.prepare(rfq=changed)["recipient_id"],candidate["recipient_id"])
        with self.assertRaises(ValueError):
            render_correspondence(changed,candidate,halted=False)
        for change in (dict(send_enabled=True),dict(independently_verified=True),dict(recipient_id="e"*64)):
            with self.assertRaises(ValueError):
                render_correspondence(draft(),dict(candidate,**change),halted=False)
        tampered=copy.deepcopy(candidate)
        tampered["recipient"]["email"]="sales@example.org"
        with self.assertRaises(ValueError):
            render_correspondence(draft(),tampered,halted=False)

    def test_persistence_replay_and_historical_scope(self):
        candidate=self.prepare()
        with RecipientStore(self.path) as store:
            saved=store.save(draft(),candidate,now=NOW,confirmed=True,halted=False)
            self.assertEqual(saved,store.save(draft(),candidate,now=NOW,confirmed=True,halted=False))
            self.assertEqual(store.list_draft(draft(region="US-NY"),halted=False)["rows"],[])
        with RecipientStore(self.path,existing_only=True) as store:
            result=store.list_draft(draft(),halted=False)
            self.assertEqual(result["rows"],[saved])
            self.assertTrue(result["historical_only"])
            self.assertFalse(result["send_enabled"])
            self.assertFalse(result["recipient_verified"])
            self.assertEqual(saved["state"],"DECLARED_RECIPIENT_DRAFT_ONLY")

    def test_confirmation_freshness_and_halt(self):
        candidate=self.prepare()
        with RecipientStore(self.path) as store:
            for value in (None,False,1):
                with self.assertRaises(PermissionError):
                    store.save(draft(),candidate,now=NOW,confirmed=value,halted=False)
            with self.assertRaises(ValueError):
                store.save(draft(),candidate,now=NOW+timedelta(days=2),confirmed=True,halted=False)
            for state in (None,True,0):
                with self.assertRaises(PermissionError):
                    self.prepare(halted=state)
                with self.assertRaises(PermissionError):
                    store.list_draft(draft(),halted=state)
            self.assertEqual(store.list_draft(draft(),halted=False)["rows"],[])

    def test_cap_and_corruption(self):
        with RecipientStore(self.path) as store:
            first=self.prepare()
            store.save(draft(),first,now=NOW,confirmed=True,halted=False)
            second=self.prepare(contact(email="sales@example.org"))
            with patch("nexus_exchange.operator_recipients.MAX_RECIPIENTS",1):
                with self.assertRaises(ValueError):
                    store.save(draft(),second,now=NOW,confirmed=True,halted=False)
            store.save(draft(),second,now=NOW,confirmed=True,halted=False)
            self.assertTrue(store.list_draft(draft(),limit=1,halted=False)["truncated"])
            store.db.execute("UPDATE operator_recipients_v1 SET payload='{}'")
            with self.assertRaises(ValueError):
                store.list_draft(draft(),halted=False)

    def test_existing_only_missing_database_and_schema(self):
        with self.assertRaises(ValueError):
            RecipientStore(self.path,existing_only=True)
        self.assertFalse(self.path.exists())
        self.path.write_bytes(b"")
        with self.assertRaises(ValueError):
            RecipientStore(self.path,existing_only=True)


    def test_storage_projection_bounds_before_decode(self):
        from nexus_exchange import operator_recipients as module
        candidate=self.prepare()
        rfq=draft()
        key=candidate["recipient_id"]
        with RecipientStore(self.path) as store:
            saved=store.save(rfq,candidate,now=NOW,confirmed=True,halted=False)
            original=store.db.execute("SELECT * FROM operator_recipients_v1").fetchone()
            reads={
                "get":lambda:store.get(rfq,key,halted=False),
                "list":lambda:store.list_draft(rfq,halted=False),
                "replay":lambda:store.save(rfq,candidate,now=NOW,confirmed=True,halted=False),
            }
            self.assertEqual(reads["get"](),saved)
            self.assertEqual(reads["list"]()["rows"],[saved])
            self.assertEqual(reads["replay"](),saved)
            cases=(
                ("payload","x"*(module.MAX_PAYLOAD+1),4,reads),
                ("payload","é"*(module.MAX_PAYLOAD//2+1),4,reads),
                ("payload",b"{}",4,reads),
                ("digest","x"*65,5,reads),
                ("recorded_at","x"*41,3,reads),
                ("recipient_id","x"*65,0,("list",)),
                ("plan_id","x"*65,1,("replay",)),
                ("draft_id","x"*65,2,("replay",)),
            )
            for column,value,index,kinds in cases:
                store.db.execute("DELETE FROM operator_recipients_v1")
                row=list(original)
                row[index]=value
                store.db.execute("INSERT INTO operator_recipients_v1 VALUES (?,?,?,?,?,?)",row)
                for kind in kinds:
                    with self.subTest(column=column,kind=kind),patch.object(module,"_decode",wraps=module._decode) as decode:
                        with self.assertRaises(ValueError):
                            reads[kind]()
                        self.assertIsNone(decode.call_args.args[0][index])
                        self.assertFalse(store.db.in_transaction)
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM operator_recipients_v1").fetchone()[0],1)

    def test_corrupt_parser_failure_is_sanitized(self):
        from nexus_exchange import operator_recipients as module
        candidate=self.prepare()
        rfq=draft()
        with RecipientStore(self.path) as store:
            store.save(rfq,candidate,now=NOW,confirmed=True,halted=False)
            for failure in (ValueError("synthetic private data"),RecursionError("synthetic private data")):
                with self.subTest(error=type(failure)),patch.object(module.json,"loads",side_effect=failure):
                    with self.assertRaisesRegex(ValueError,"^recipient storage validation failed$"):
                        store.get(rfq,candidate["recipient_id"],halted=False)

    def test_recipient_save_rejects_silent_insert_suppression_and_rewrite(self):
        rfq=draft()
        candidate=self.prepare()
        with RecipientStore(self.path) as store:
            for statement in (
                "CREATE TRIGGER bad BEFORE INSERT ON operator_recipients_v1 "
                "BEGIN SELECT RAISE(IGNORE); END",
                "CREATE TRIGGER bad AFTER INSERT ON operator_recipients_v1 "
                "BEGIN UPDATE operator_recipients_v1 SET payload='{}'; END",
                "CREATE TEMP TRIGGER bad BEFORE INSERT ON operator_recipients_v1 "
                "BEGIN SELECT RAISE(IGNORE); END",
            ):
                with self.subTest(statement=statement):
                    store.db.execute(statement)
                    try:
                        with self.assertRaisesRegex(ValueError,"unexpected recipient storage trigger"):
                            store.save(rfq,candidate,now=NOW,confirmed=True,halted=False)
                        self.assertFalse(store.db.in_transaction)
                        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM operator_recipients_v1").fetchone()[0],0)
                    finally:
                        store.db.execute("DROP TRIGGER bad")
            saved=store.save(rfq,candidate,now=NOW,confirmed=True,halted=False)
            self.assertEqual(saved,store.get(rfq,candidate["recipient_id"],halted=False))
            self.assertEqual(saved,store.save(rfq,candidate,now=NOW,confirmed=True,halted=False))
            self.assertFalse(saved["send_enabled"])
            self.assertFalse(saved["external_authority"])

    def test_recipient_replay_rejects_trigger_without_mutating_existing_record(self):
        rfq=draft()
        candidate=self.prepare()
        with RecipientStore(self.path) as store:
            saved=store.save(rfq,candidate,now=NOW,confirmed=True,halted=False)
            store.db.execute("CREATE TRIGGER bad AFTER INSERT ON operator_recipients_v1 "
                             "BEGIN DELETE FROM operator_recipients_v1; END")
            with self.assertRaisesRegex(ValueError,"unexpected recipient storage trigger"):
                store.save(rfq,candidate,now=NOW,confirmed=True,halted=False)
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(saved,store.get(rfq,candidate["recipient_id"],halted=False))
        with RecipientStore(self.path,existing_only=True) as store:
            self.assertEqual(saved,store.get(rfq,candidate["recipient_id"],halted=False))
