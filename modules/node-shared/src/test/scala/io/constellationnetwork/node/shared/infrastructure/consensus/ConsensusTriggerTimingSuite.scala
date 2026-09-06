package io.constellationnetwork.node.shared.infrastructure.consensus

import cats.effect.IO
import cats.effect.testkit.TestControl
import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.config.types.{ConsensusConfig, EventCutterConfig}
import io.constellationnetwork.node.shared.infrastructure.consensus.declaration.Facility
import io.constellationnetwork.node.shared.infrastructure.consensus.trigger.{ConsensusTrigger, EventTrigger, TimeTrigger}
import io.constellationnetwork.schema.SnapshotOrdinal
import io.constellationnetwork.schema.peer.PeerId
import io.constellationnetwork.security.hash.Hash
import io.constellationnetwork.security.hex.Hex

import eu.timepit.refined.auto._
import weaver.SimpleIOSuite

object ConsensusTriggerTimingSuite extends SimpleIOSuite {
  private val legacy = ConsensusConfig(43.seconds, 50.seconds, 3L, 10.seconds, 10.seconds, EventCutterConfig(1024, 100))
  private val periodic = legacy.copy(timeTriggerPeriod = Some(65.seconds))
  private val peer = PeerId(Hex("1" * 128))
  private val outsider = PeerId(Hex("f" * 128))
  private val idle = ConsensusState(1, (), Facilitators(List(peer)), (), Duration.Zero, spreadAckKinds = Set.empty[Unit])

  private def resources(sender: PeerId, trigger: Option[ConsensusTrigger]) =
    ConsensusResources.empty[IO, String, Unit].map { resources =>
      resources.copy(peerDeclarationsMap = Map(sender -> PeerDeclarations.empty.copy(facility = Some(
        Facility(Map.empty, Candidates(Set.empty), trigger, Hash.empty, SnapshotOrdinal.MinValue)
      ))))
    }

  test("idle observation does not start the enabled stall clock; legacy mode retains its old behavior") {
    TestControl.executeEmbed {
      for {
        r <- resources(peer, None)
        _ <- IO.sleep(60.seconds)
        observed <- ConsensusTimeTrigger.observeTriggers(idle, r)
      } yield expect.same(observed, idle) &&
        expect(!ConsensusTimeTrigger.shouldDetectStall(periodic, observed)) &&
        expect(ConsensusTimeTrigger.shouldDetectStall(legacy, observed))
    }
  }

  test("a late observer anchors the period to the real timed trigger, not early state creation") {
    TestControl.executeEmbed {
      for {
        _ <- IO.sleep(60.seconds)
        r <- resources(peer, Some(TimeTrigger))
        observed <- ConsensusTimeTrigger.observeTriggers(idle, r)
      } yield expect.same(observed.triggerStartedAt, Some(60.seconds)) &&
        expect.same(observed.timeTriggerStartedAt, Some(60.seconds)) &&
        expect(ConsensusTimeTrigger.shouldDetectStall(periodic, observed)) &&
        expect.same(ConsensusTimeTrigger.nextDeadline(periodic, 65.seconds, observed.timeTriggerStartedAt), 125.seconds)
    }
  }

  test("an outsider cannot start either clock") {
    resources(outsider, Some(TimeTrigger)).flatMap(ConsensusTimeTrigger.observeTriggers(idle, _)).map { observed =>
      expect.same(observed, idle)
    }
  }

  test("an event starts recovery timing but not the timed-period clock") {
    TestControl.executeEmbed {
      for {
        _ <- IO.sleep(10.seconds)
        r <- resources(peer, Some(EventTrigger))
        observed <- ConsensusTimeTrigger.observeTriggers(idle, r)
      } yield expect.same(observed.triggerStartedAt, Some(10.seconds)) && expect(observed.timeTriggerStartedAt.isEmpty)
    }
  }

  test("later timed gossip does not reset an already running event or timed clock") {
    TestControl.executeEmbed {
      for {
        _ <- IO.sleep(10.seconds)
        event <- resources(peer, Some(EventTrigger))
        active <- ConsensusTimeTrigger.observeTriggers(idle, event)
        _ <- IO.sleep(10.seconds)
        timed <- resources(peer, Some(TimeTrigger))
        first <- ConsensusTimeTrigger.observeTriggers(active, timed)
        _ <- IO.sleep(100.seconds)
        duplicate <- ConsensusTimeTrigger.observeTriggers(first, timed)
      } yield expect.same(first.triggerStartedAt, Some(10.seconds)) &&
        expect.same(first.timeTriggerStartedAt, Some(20.seconds)) && expect.same(first, duplicate)
    }
  }

  test("pre-received declarations are timestamped when observed in the active local round") {
    TestControl.executeEmbed {
      for {
        early <- resources(peer, Some(TimeTrigger))
        _ <- IO.sleep(120.seconds)
        observed <- ConsensusTimeTrigger.observeTriggers(idle, early)
      } yield expect.same(observed.timeTriggerStartedAt, Some(120.seconds))
    }
  }

  test("a node's own timed start is preserved when peer declarations arrive later") {
    val own = idle.copy(triggerStartedAt = Some(Duration.Zero), timeTriggerStartedAt = Some(Duration.Zero))
    TestControl.executeEmbed {
      for {
        _ <- IO.sleep(60.seconds)
        r <- resources(peer, Some(TimeTrigger))
        observed <- ConsensusTimeTrigger.observeTriggers(own, r)
      } yield expect.same(observed, own)
    }
  }
}
