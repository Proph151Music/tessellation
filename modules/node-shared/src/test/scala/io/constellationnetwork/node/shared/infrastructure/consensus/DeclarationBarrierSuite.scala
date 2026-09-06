package io.constellationnetwork.node.shared.infrastructure.consensus

import cats.data.StateT
import cats.effect.IO
import cats.effect.testkit.TestControl
import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.config.types.{ConsensusConfig, EventCutterConfig}
import io.constellationnetwork.node.shared.infrastructure.consensus.declaration.Proposal
import io.constellationnetwork.schema.peer.PeerId
import io.constellationnetwork.security.hash.Hash
import io.constellationnetwork.security.hex.Hex

import eu.timepit.refined.auto._
import weaver.SimpleIOSuite

/** Regression guards for the existing all-facilitator declaration barrier. */
object DeclarationBarrierSuite extends SimpleIOSuite {
  private val config = ConsensusConfig(43.seconds, 50.seconds, 3L, 10.seconds, 10.seconds, EventCutterConfig(1024, 100))
  private val peers = (1 to 5).toList.map(i => PeerId(Hex(f"$i%0128x")))
  private val proposal = Proposal(Hash.empty, Hash.empty)
  private val state = ConsensusState(1, (), Facilitators(peers), (), Duration.Zero, spreadAckKinds = Set.empty[Unit])

  private val advancer = new ConsensusStateAdvancer[IO, Int, String, Unit, Unit, Unit, Unit] {
    def getConsensusOutcome(state: State): Option[(Previous[Int], Unit)] = None
    def advanceStatus(resources: Resources): StateT[IO, State, IO[Unit]] = StateT.pure(IO.unit)
    def collect(resources: Resources) = maybeGetAllDeclarations(state, resources, config)(_.proposal)
  }

  private def resources(ids: List[PeerId]) = ConsensusResources[String, Unit](
    peerDeclarationsMap = ids.map(_ -> PeerDeclarations.empty.copy(proposal = Some(proposal))).toMap,
    acksMap = Map.empty,
    withdrawalsMap = Map.empty,
    ackKinds = Set.empty,
    artifacts = Map.empty,
    updatedAt = Duration.Zero
  )

  test("one missing facilitator blocks both before and after the ten-second stale warning") {
    TestControl.executeEmbed {
      for {
        before <- advancer.collect(resources(peers.dropRight(1)))
        _ <- IO.sleep(11.seconds)
        stale <- advancer.collect(resources(peers.dropRight(1)))
        complete <- advancer.collect(resources(peers))
      } yield expect(before.isEmpty) && expect(stale.isEmpty) && expect.same(complete.map(_.keySet), Some(peers.toSet))
    }
  }

  test("an outsider declaration cannot replace a missing facilitator") {
    val outsider = PeerId(Hex("f" * 128))
    TestControl.executeEmbed {
      IO.sleep(60.seconds) >> advancer.collect(resources(peers.dropRight(1) :+ outsider)).map(r => expect(r.isEmpty))
    }
  }

  test("a single received proposal is never enough to advance a five-node phase") {
    TestControl.executeEmbed {
      IO.sleep(60.seconds) >> advancer.collect(resources(peers.take(1))).map(r => expect(r.isEmpty))
    }
  }
}
