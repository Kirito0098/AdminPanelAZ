from app.services.node_sync.reconcile_worker import classify_heal_actions


def test_classify_heal_actions_marks_wireguard_crypto_drift_healable():
    verify_result = {
        "replicas": [
            {
                "mismatches": [
                    {"kind": "fingerprint", "path": "wireguard/conf_files"},
                ],
            }
        ],
    }

    actions, unhealable_only = classify_heal_actions(verify_result)

    assert unhealable_only is False
    assert "crypto_sync" in actions


def test_classify_heal_actions_marks_client_list_drift_as_crypto_sync():
    verify_result = {
        "replicas": [
            {
                "mismatches": [
                    {"kind": "wireguard_clients", "missing_on_replica": ["alice"]},
                ],
            }
        ],
    }

    actions, unhealable_only = classify_heal_actions(verify_result)

    assert unhealable_only is False
    assert "crypto_sync" in actions
    assert "policy" in actions


def test_classify_heal_actions_offline_node_still_unhealable():
    verify_result = {
        "replicas": [
            {
                "mismatches": [
                    {"kind": "node_status", "detail": "offline"},
                ],
            }
        ],
    }

    actions, unhealable_only = classify_heal_actions(verify_result)

    assert actions == set()
    assert unhealable_only is True
