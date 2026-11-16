#!/usr/bin/env python3
"""Opt-in multi-node Kind qualification, using ONLY a fresh disposable cluster.

Create it with the config in scripts/partition-fixture/kind.yaml and --retain. This
script refuses pre-existing non-system workloads. It never deletes resources.
Kubeconfig, image build output and all evidence stay private in the run directory.
Only worker->control-plane:6443 OUTPUT/FORWARD rules are changed (IPv4 and IPv6). No host
firewall operation is performed. SIGINT/SIGTERM restore those exact owned rules;
SIGKILL/host failure cannot run finally: the printed recovery command is retained.
"""

import argparse
import datetime
import ipaddress
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import time


def command(*args, data=None, timeout=60, check=True):
    result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        # Commands use disposable fixture arguments only; never dump kubeconfigs or env.
        raise RuntimeError(f"{args[0]} {args[1:4]} failed: {result.stderr[-1500:]}")
    return result


def wait_for(description, predicate, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(2)
    raise AssertionError(f"Timed out: {description}")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Probe:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.evidence).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.kubeconfig = self.root / "kubeconfig"
        self.victim = args.cluster + "-worker"
        self.healthy = args.cluster + "-worker2"
        self.control = args.cluster + "-control-plane"
        self.tag = args.cluster
        self.rules = []
        self.events = []
        self.old = {}
        self.started = time.monotonic()

    def event(self, kind, **data):
        row = dict(event=kind, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), elapsed_seconds=round(time.monotonic() - self.started, 2), **data)
        self.events.append(row)
        with (self.root / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)

    def k(self, *args, data=None, check=True):
        return command("kubectl", "--kubeconfig", str(self.kubeconfig), "--request-timeout=15s", *args, data=data, check=check).stdout.strip()

    def get(self, resource, *args):
        return json.loads(self.k("get", resource, *args, "-o", "json"))

    def apply(self, obj):
        self.k("create", "-f", "-", data=json.dumps(obj))

    def sql(self, namespace, query, check=True):
        return self.k("-n", namespace, "exec", "deployment/database", "--", "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "owlmast", "-tAc", query, check=check)

    def number(self, ns, query):
        return int(self.sql(ns, query))

    def pods(self, ns):
        return self.get("pods", "-n", ns, "-l", "app=worker")["items"]

    def snapshot(self, name):
        nodes = self.get("nodes")
        pods = self.get("pods", "-A")
        deployments = self.get("deployments", "-A")
        # No Secrets, env values or raw application logs are exported.
        report = {
            "nodes": [dict(name=n["metadata"]["name"], taints=n["spec"].get("taints", []), conditions=n["status"]["conditions"]) for n in nodes["items"]],
            "pods": [
                dict(
                    namespace=p["metadata"]["namespace"],
                    name=p["metadata"]["name"],
                    uid=p["metadata"]["uid"],
                    deletion=p["metadata"].get("deletionTimestamp"),
                    node=p["spec"].get("nodeName"),
                    tolerations=p["spec"].get("tolerations"),
                    status=p.get("status"),
                )
                for p in pods["items"]
            ],
            "deployments": [
                dict(namespace=d["metadata"]["namespace"], name=d["metadata"]["name"], generation=d["metadata"]["generation"], strategy=d["spec"]["strategy"], status=d.get("status"))
                for d in deployments["items"]
            ],
        }
        (self.root / (name + ".json")).write_text(json.dumps(report, indent=2))
        return report

    def prepare(self):
        require(re.fullmatch(r"owl-pr189-partition-[a-z0-9-]+", self.args.cluster), "unsafe cluster name")
        require(not (self.root / "events.jsonl").exists(), "evidence directory already used")
        config = command("kind", "get", "kubeconfig", "--name", self.args.cluster).stdout
        self.kubeconfig.write_text(config)
        self.kubeconfig.chmod(0o600)
        nodes = self.get("nodes")["items"]
        require({n["metadata"]["name"] for n in nodes} == {self.control, self.victim, self.healthy}, "expected exactly the fresh three-node Kind cluster")
        allowed = {"kube-system", "local-path-storage"}
        require(all(p["metadata"]["namespace"] in allowed for p in self.get("pods", "-A")["items"]), "refusing cluster with existing user workloads")
        require(all(n["metadata"]["name"] in allowed | {"default", "kube-public", "kube-node-lease"} for n in self.get("namespaces")["items"]), "refusing previously used cluster")
        for node in (self.control, self.victim, self.healthy):
            label = command("docker", "inspect", node, "--format", '{{index .Config.Labels "io.x-k8s.kind.cluster"}}').stdout.strip()
            require(label == self.args.cluster, "Docker node ownership mismatch")
        self.cp_ip = command("docker", "inspect", self.control, "--format", '{{(index .NetworkSettings.Networks "kind").IPAddress}}').stdout.strip()
        require(ipaddress.ip_address(self.cp_ip).version == 4, "IPv4 required")
        ipv6 = command("docker", "inspect", self.control, "--format", '{{(index .NetworkSettings.Networks "kind").GlobalIPv6Address}}').stdout.strip()
        self.endpoints = [self.cp_ip] + ([str(ipaddress.IPv6Address(ipv6))] if ipv6 else [])
        resolved = {line.split()[0] for line in command("docker", "exec", self.victim, "getent", "ahosts", self.control).stdout.splitlines()}
        require(resolved and resolved <= set(self.endpoints), "API hostname resolves outside owned container endpoints")
        for endpoint in self.endpoints:
            command("docker", "exec", self.victim, "timeout", "5", "bash", "-c", f"</dev/tcp/{endpoint}/6443")
        for image in (self.args.image, "tensorchord/vchord-postgres:pg18-v1.1.1"):
            command("kind", "load", "docker-image", image, "--name", self.args.cluster, timeout=240)
        image_id = command("docker", "image", "inspect", self.args.image, "--format", "{{.Id}}").stdout.strip()
        self.event(
            "prepared",
            cluster=self.args.cluster,
            control_endpoints=self.endpoints,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            image_id=image_id,
            source_head=command("git", "rev-parse", "HEAD").stdout.strip(),
        )
        for ns, mode, extra in [("replacement", "finish-after-reclaimed", 60), ("rollout", "slow", 1800)]:
            self.setup(ns, mode, extra)
        self.snapshot("before-partition")

    def deployment(self, ns, name, container, node=None):
        spec = dict(containers=[container])
        if node:
            spec.update(nodeSelector={"kubernetes.io/hostname": node}, tolerations=[dict(key="node-role.kubernetes.io/control-plane", operator="Exists", effect="NoSchedule")])
        else:
            spec["affinity"] = {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [{"matchExpressions": [{"key": "kubernetes.io/hostname", "operator": "In", "values": [self.victim, self.healthy]}]}]
                    },
                    "preferredDuringSchedulingIgnoredDuringExecution": [
                        {"weight": 100, "preference": {"matchExpressions": [{"key": "kubernetes.io/hostname", "operator": "In", "values": [self.victim]}]}}
                    ],
                }
            }
        return dict(
            apiVersion="apps/v1",
            kind="Deployment",
            metadata=dict(name=name, namespace=ns),
            spec=dict(replicas=1, strategy=dict(type="Recreate"), selector=dict(matchLabels=dict(app=name)), template=dict(metadata=dict(labels=dict(app=name)), spec=spec)),
        )

    def setup(self, ns, mode, extra):
        self.apply(dict(apiVersion="v1", kind="Namespace", metadata=dict(name=ns)))
        db = dict(
            name="database",
            image="tensorchord/vchord-postgres:pg18-v1.1.1",
            imagePullPolicy="Never",
            env=[dict(name="POSTGRES_HOST_AUTH_METHOD", value="trust"), dict(name="POSTGRES_DB", value="owlmast")],
        )
        self.apply(self.deployment(ns, "database", db, self.control))
        self.apply(dict(apiVersion="v1", kind="Service", metadata=dict(name="database", namespace=ns), spec=dict(selector=dict(app="database"), ports=[dict(port=5432)])))
        wait_for("DB ready", lambda: self.sql(ns, "select 1", check=False) == "1")
        common = [
            "--spring.r2dbc.url=r2dbc:postgresql://database:5432/owlmast",
            "--spring.r2dbc.username=postgres",
            "--spring.flyway.url=jdbc:postgresql://database:5432/owlmast",
            "--spring.flyway.user=postgres",
            "--server.port=8080",
            "--owlmast.jobs.poll-interval=PT0.2S",
            "--owlmast.jobs.lease-duration=PT20M",
            "--fixture.effect-log=true",
            "--fixture.deduplicate=true",
            "--owlmast.jobs.instance-id=$(POD_NAME)",
        ]
        env = [dict(name="POD_NAME", valueFrom=dict(fieldRef=dict(fieldPath="metadata.name")))]
        seed = dict(
            name="backend",
            image=self.args.image,
            imagePullPolicy="Never",
            env=env,
            args=common + ["--fixture.seed=true", f"--fixture.extra-follow-ups={extra}", "--owlmast.jobs.scheduler.enabled=false"],
        )
        self.apply(self.deployment(ns, "seed", seed, self.control))
        wait_for("seed completed", lambda: self.sql(ns, "select count(*) from jobs.work_item", check=False) == str(extra + 7))
        self.k("-n", ns, "scale", "deployment/seed", "--replicas=0")
        # Persist claims independently of final attempt counters, and inspect stale terminal writes.
        self.sql(
            ns,
            """create table partition_claims (item_id uuid, owner text, token uuid, at timestamptz default clock_timestamp());
          create function partition_claim() returns trigger language plpgsql as $$ begin
          if NEW.status = 'RUNNING' and NEW.lease_token is distinct from OLD.lease_token then
          insert into partition_claims(item_id,owner,token) values(NEW.id,NEW.lease_owner,NEW.lease_token); end if;
          return NEW; end $$;
          create trigger partition_claim after update on jobs.work_item for each row execute function partition_claim();""",
        )
        worker = dict(seed, args=common + [f"--fixture.mode={mode}", "--owlmast.jobs.scheduler.enabled=true"])
        resource = self.deployment(ns, "worker", worker)
        if ns == "replacement":
            # A standalone ReplicaSet permits replacement-only handler configuration without
            # asking a Deployment controller to roll the old pod. Production Deployments use
            # this same ReplicaSet controller, but this fixture is not the production chart.
            resource["kind"] = "ReplicaSet"
            del resource["spec"]["strategy"]
        self.apply(resource)

        def running():
            pods = self.pods(ns)
            return pods[0] if pods and pods[0]["status"].get("phase") == "Running" else None

        pod = wait_for("worker running", running)
        require(pod["spec"]["nodeName"] == self.victim, "initial worker must run on victim")
        wait_for("work in flight", lambda: self.number(ns, "select count(*) from jobs.work_item where status='RUNNING'") > 0)
        tolerations = {t["key"]: t for t in pod["spec"].get("tolerations", [])}
        for key in ("node.kubernetes.io/not-ready", "node.kubernetes.io/unreachable"):
            require(tolerations[key].get("tolerationSeconds") == 300, "expected default 300s toleration")
        cid = pod["status"]["containerStatuses"][0]["containerID"].removeprefix("containerd://")
        self.old[ns] = dict(name=pod["metadata"]["name"], uid=pod["metadata"]["uid"], ip=pod["status"]["podIP"], container=cid, total=extra + 7, effects=extra + 4)
        if ns == "replacement":
            self.old[ns]["held"] = self.sql(ns, "select id from jobs.work_item where status='RUNNING'")
            require(len(self.old[ns]["held"].splitlines()) == 1, "one held item expected")
            # Replacement uses normal behavior; change only after the original is running without
            # triggering a Deployment rollout: the ReplicaSet template supplies replacement pods.
            rs = pod["metadata"]["ownerReferences"][0]["name"]
            normal = common + ["--fixture.mode=normal", "--owlmast.jobs.scheduler.enabled=true"]
            patch = {"spec": {"template": {"spec": {"containers": [dict(name="backend", args=normal)]}}}}
            self.k("-n", ns, "patch", "replicaset", rs, "--type=strategic", "-p", json.dumps(patch))
        self.event("work-in-flight", namespace=ns, old=self.old[ns], tolerations=pod["spec"]["tolerations"])

    def rule_command(self, chain, action, address):
        ip = ipaddress.ip_address(address)
        return [
            "docker",
            "exec",
            self.victim,
            "iptables" if ip.version == 4 else "ip6tables",
            "-w",
            "5",
            action,
            chain,
            "-d",
            str(ip) + ("/32" if ip.version == 4 else "/128"),
            "-p",
            "tcp",
            "--dport",
            "6443",
            "-m",
            "comment",
            "--comment",
            self.tag,
            "-j",
            "DROP",
        ]

    def iptables(self, rule, action, check=True):
        chain, address = rule
        return command(*self.rule_command(chain, action, address), check=check)

    def fault(self):
        intended = [(chain, address) for address in self.endpoints for chain in ("OUTPUT", "FORWARD")]
        recovery = "\n".join(" ".join(self.rule_command(chain, "-D", address)) for chain, address in intended) + "\n"
        (self.root / "restore-network.sh").write_text("#!/bin/sh\n" + recovery)
        for rule in intended:
            require(self.iptables(rule, "-C", check=False).returncode == 1, "rule already exists or check failed")
            self.rules.append(rule)
            self.iptables(rule, "-I")
        self.fault_start = time.monotonic()
        for address in self.endpoints:
            probe = command("docker", "exec", self.victim, "timeout", "3", "bash", "-c", f"</dev/tcp/{address}/6443", check=False)
            require(probe.returncode == 124, "API connection did not time out under DROP")
        self.event("partition-installed", api_connect_returncode=124, endpoints=self.endpoints, rules=self.rules)

    def alive_and_connected(self, ns):
        old = self.old[ns]
        state = json.loads(command("docker", "exec", self.victim, "crictl", "inspect", old["container"]).stdout)
        require(state["status"]["state"] == "CONTAINER_RUNNING", "old container stopped during partition")
        count = self.number(ns, f"select count(*) from pg_stat_activity where client_addr='{old['ip']}'::inet")
        # Connections may close between statements. Committed, instance-specific writes
        # below prove DB access even when this point-in-time session count is zero.
        if ns == "replacement":
            recent = self.number(ns, f"select count(*) from fixture_worker_heartbeat where instance='{old['name']}' and observed_at > clock_timestamp()-interval '10 seconds'")
        else:
            recent = self.number(ns, f"select count(*) from fixture_effect_log where instance='{old['name']}' and recorded_at > clock_timestamp()-interval '10 seconds'")
        require(recent > 0, "old backend has no recent committed PostgreSQL observation")
        return dict(container_state=state["status"]["state"], db_sessions=count, recent_committed_observations=recent)

    def partition_scenarios(self):
        def tainted():
            node = self.get("node", self.victim)
            taints = node["spec"].get("taints", [])
            return taints if any(t["key"] == "node.kubernetes.io/unreachable" and t["effect"] == "NoExecute" for t in taints) else None

        taints = wait_for("unreachable NoExecute taint", tainted, 120)
        self.event("unreachable", taints=taints, live={ns: self.alive_and_connected(ns) for ns in self.old})
        before = self.number("rollout", "select count(*) from fixture_effect_log")
        # Same build, changed pod template: this tests controller Recreate behavior, not a schema upgrade.
        self.k("-n", "rollout", "patch", "deployment", "worker", "--type=merge", "-p", json.dumps({"spec": {"template": {"metadata": {"annotations": {"partition-qualification": self.tag}}}}}))
        self.event("rollout-requested", effects_before=before)

        def replacement_ready():
            for p in self.pods("replacement"):
                if p["metadata"]["uid"] != self.old["replacement"]["uid"] and p["status"].get("phase") == "Running":
                    if self.sql("replacement", "select count(*) from partition_claims where owner not like '%" + self.old["replacement"]["name"] + "%'") != "0":
                        return p
            return None

        replacement = wait_for("replacement running and claiming", replacement_ready, 430)
        require(replacement["spec"]["nodeName"] == self.healthy, "replacement must use healthy node")
        self.event(
            "replacement-running",
            pod=replacement["metadata"]["name"],
            node=replacement["spec"]["nodeName"],
            partition_seconds=round(time.monotonic() - self.fault_start, 2),
            live={ns: self.alive_and_connected(ns) for ns in self.old},
        )
        require(self.number("rollout", "select count(*) from fixture_effect_log") > before, "partitioned rollout worker must continue DB-backed effects")
        held = self.old["replacement"]["held"]
        wait_for("all except held item complete", lambda: self.number("replacement", "select count(*) from jobs.work_item where status<>'SUCCEEDED'") == 1)
        row = self.sql("replacement", f"select row_to_json(w) from jobs.work_item w where id='{held}'")
        lease = json.loads(row)
        require(lease["status"] == "RUNNING" and self.old["replacement"]["name"] in lease["lease_owner"], "replacement stole live lease")
        require(self.number("replacement", f"select count(*) from jobs.work_item where id='{held}' and lease_expires_at>clock_timestamp()") == 1, "held lease must still be live")
        # Deliberate fixture-only stale-lease injection. API partition alone does not expire a
        # DB-connected worker's lease. This diagnostic is NOT natural lease-expiry evidence.
        self.sql("replacement", f"update jobs.work_item set lease_expires_at=clock_timestamp()-interval '1 second' where id='{held}'")
        wait_for("two deliveries for stale completion", lambda: self.number("replacement", f"select count(*) from fixture_effect_log where item_id='{held}'") == 2)
        logs = command("docker", "exec", self.victim, "crictl", "logs", self.old["replacement"]["container"]).stdout
        require(f"Work item {held} (fixture.follow-up) lost its lease before completion; the write changed nothing" in logs, "missing stale-write rejection evidence")
        terminal = self.sql("replacement", f"select row_to_json(w) from jobs.work_item w where id='{held}'")
        completed = json.loads(terminal)
        require(
            completed["status"] == "SUCCEEDED" and completed["lease_token"] is None and replacement["metadata"]["name"] in completed["lease_owner"] and completed["attempt_count"] == 2,
            "replacement terminal row not protected",
        )
        time.sleep(3)
        require(self.sql("replacement", f"select row_to_json(w) from jobs.work_item w where id='{held}'") == terminal, "terminal row changed after stale completion")
        self.event("fencing", injection="fixture-only lease_expires_at set into past", held_item=held, stale_write_rejected=True, terminal=completed, old_live=self.alive_and_connected("replacement"))
        self.validate_queue("replacement")
        rollout_pods = self.pods("rollout")
        self.event(
            "rollout-during-partition",
            pods=[
                dict(name=p["metadata"]["name"], uid=p["metadata"]["uid"], deletion=p["metadata"].get("deletionTimestamp"), node=p["spec"].get("nodeName"), phase=p["status"].get("phase"))
                for p in rollout_pods
            ],
            old_live=self.alive_and_connected("rollout"),
            remaining=self.number("rollout", "select count(*) from jobs.work_item where status<>'SUCCEEDED'"),
        )
        require(any(p["metadata"]["uid"] == self.old["rollout"]["uid"] and p["metadata"].get("deletionTimestamp") for p in rollout_pods), "expected terminating old rollout pod")
        require(not any(p["metadata"]["uid"] != self.old["rollout"]["uid"] for p in rollout_pods), "unexpected rollout successor: inspect behavior before claiming Recreate blocks")
        self.snapshot("during-partition")
        rules = "\n".join(command("docker", "exec", self.victim, binary, "-c").stdout for binary in ("iptables-save", "ip6tables-save"))
        (self.root / "owned-rules.txt").write_text("\n".join(line for line in rules.splitlines() if self.tag in line) + "\n")
        self.event("partition-observed", duration_seconds=round(time.monotonic() - self.fault_start, 2))

    def validate_queue(self, ns):
        old = self.old[ns]
        counts = dict(
            total=self.number(ns, "select count(*) from jobs.work_item"),
            unfinished=self.number(ns, "select count(*) from jobs.work_item where status<>'SUCCEEDED'"),
            receiver_effects=self.number(ns, "select count(*) from fixture_receiver_effect"),
            distinct_deliveries=self.number(ns, "select count(distinct idempotency_key) from fixture_effect_log"),
            deliveries=self.number(ns, "select count(*) from fixture_effect_log"),
            audit_events=self.number(ns, "select count(*) from audit.event"),
        )
        require(
            counts["total"] == old["total"]
            and counts["unfinished"] == 0
            and counts["receiver_effects"] == old["effects"]
            and counts["distinct_deliveries"] == old["effects"]
            and counts["audit_events"] == 3,
            f"queue/effect invariant failed: {counts}",
        )
        self.event("queue-verified", namespace=ns, **counts)

    def restore(self):
        failures = []
        for chain in list(self.rules):
            try:
                exists = self.iptables(chain, "-C", check=False)
                if exists.returncode == 0:
                    self.iptables(chain, "-D")
                require(self.iptables(chain, "-C", check=False).returncode == 1, "rule still present or check failed")
                self.rules.remove(chain)
            except Exception as error:
                failures.append(f"{chain}: {error}")
        self.event("network-restoration", remaining_rules=self.rules, failures=failures)
        require(not failures, "RESTORATION FAILED; run retained restore-network.sh after checking ownership")

    def recovered(self):
        for endpoint in self.endpoints:
            command("docker", "exec", self.victim, "timeout", "5", "bash", "-c", f"</dev/tcp/{endpoint}/6443")
        self.k("wait", "--for=condition=Ready", "node/" + self.victim, "--timeout=120s")
        self.k("-n", "rollout", "rollout", "status", "deployment/worker", "--timeout=180s")

        def successor():
            return any(p["metadata"]["uid"] != self.old["rollout"]["uid"] and p["status"].get("phase") == "Running" for p in self.pods("rollout"))

        wait_for("rollout successor after restore", successor)
        wait_for("rollout queue drained", lambda: self.number("rollout", "select count(*) from jobs.work_item where status<>'SUCCEEDED'") == 0, 700)
        self.validate_queue("rollout")
        self.validate_queue("replacement")
        self.snapshot("recovered")
        for ns in self.old:
            resource = "replicaset/worker" if ns == "replacement" else "deployment/worker"
            self.k("-n", ns, "scale", resource, "--replicas=0")
        wait_for("workers stopped", lambda: all(not self.pods(ns) for ns in self.old), 120)
        self.event("PASS", retained_cluster=self.args.cluster, retained_namespaces=list(self.old), workers_scaled_to_zero=True, background_processes_started=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise InterruptedError(f"signal {signum}; restoring scoped network access")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    probe = Probe(args)
    probe.prepare()
    try:
        probe.fault()
        probe.partition_scenarios()
    finally:
        probe.restore()
    probe.recovered()


if __name__ == "__main__":
    main()
