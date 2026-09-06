package io.constellationnetwork.node.shared.infrastructure.consensus.update

import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.infrastructure.consensus._
import io.constellationnetwork.schema.peer.PeerId
import io.constellationnetwork.security.hash.Hash
import io.constellationnetwork.security.hex.Hex

import org.scalacheck.Arbitrary.arbitrary
import org.scalacheck.Gen
import weaver.SimpleIOSuite
import weaver.scalacheck.{CheckConfig, Checkers}

object UnlockConsensusUpdateSuite extends SimpleIOSuite with Checkers {

  type Key = Int
  type Artifact = Unit
  type Context = Unit
  type Status = Either[Unit, Unit]
  type Outcome = Unit
  type Kind = Unit

  val unlockConsensusFn: ConsensusStateUpdateFn[UnlockConsensusUpdateSuite.F, Key, Artifact, Status, Outcome, Kind, Unit] =
    (resources: ConsensusResources[Artifact, Kind]) =>
      UnlockConsensusUpdate.tryUnlock[F, ConsensusState[Key, Status, Outcome, Kind], Kind](resources.acksMap)(
        _.status match {
          case Left(_)  => ().some
          case Right(_) => none
        }
      )

  override def checkConfig: CheckConfig = CheckConfig.default.copy(minimumSuccessful = 40)

  private val fivePeers = (1 to 5).toList.map(i => PeerId(Hex(f"$i%0128x")))
  private val fivePeerState = ConsensusState[Key, Status, Outcome, Kind](
    1,
    (),
    Facilitators(fivePeers),
    Left(()),
    Duration.Zero,
    lockStatus = LockStatus.Closed,
    spreadAckKinds = Set.empty
  )

  test("outsider acknowledgments cannot complete a five-facilitator recovery decision") {
    val received = fivePeers.dropRight(1).toSet
    val outsider = PeerId(Hex("f" * 128))
    val acks = (fivePeers.take(2) :+ outsider).map(peer => (peer, ()) -> received).toMap
    UnlockConsensusUpdate.tryUnlock[F, ConsensusState[Key, Status, Outcome, Kind], Kind](acks)(_ => Some(())).run(fivePeerState).map {
      case (state, _) => expect.same(state, fivePeerState)
    }
  }

  test("existing recovery requires three current facilitators to remove one missing peer from five") {
    val received = fivePeers.dropRight(1).toSet
    val acks = fivePeers.take(3).map(peer => (peer, ()) -> received).toMap
    UnlockConsensusUpdate.tryUnlock[F, ConsensusState[Key, Status, Outcome, Kind], Kind](acks)(_ => Some(())).run(fivePeerState).map {
      case (state, _) =>
        expect.same(state.lockStatus, LockStatus.Reopened) &&
        expect.same(state.facilitators.value.toSet, received) &&
        expect.same(state.removedFacilitators.value, fivePeers.takeRight(1).toSet)
    }
  }

  test("state either transitions to target state or remains in initial state, regardless of what subset of acks is processed") {
    forall(lockedStateAndResourcesGen) {
      case (initialState, resources) =>
        unlockConsensusFn(resources).run(initialState).flatMap {
          case (targetState, _) =>
            val partialResourcesGen =
              Gen.someOf(resources.acksMap).map(_.toMap).map(partialAcksMap => resources.copy(acksMap = partialAcksMap))

            forall(partialResourcesGen) { partialResources =>
              unlockConsensusFn(partialResources).run(initialState).map {
                case (state, _) =>
                  expect.same(initialState, state).xor(expect.same(targetState, state))
              }
            }
        }
    }
  }

  test("state transitions to reopened and removed facilitators are disjoint with facilitators") {
    forall(lockedStateAndResourcesGen) {
      case (initialState, resources) =>
        unlockConsensusFn(resources).run(initialState).map {
          case (state, _) =>
            expect(state.lockStatus === LockStatus.Reopened) &&
            expect(state.removedFacilitators.value.union(state.facilitators.value.toSet) === initialState.facilitators.value.toSet) &&
            expect(state.removedFacilitators.value.intersect(state.facilitators.value.toSet) === Set.empty)
        }
    }
  }

  def lockedStateAndResourcesGen: Gen[(ConsensusState[Key, Status, Outcome, Kind], ConsensusResources[Artifact, Kind])] =
    for {
      facilitators <- facilitatorsGen
      state <- lockedStateGen(facilitators)
      acksMap <- acksMapGen(facilitators)
      resources = ConsensusResources(
        peerDeclarationsMap = Map.empty,
        acksMap = acksMap,
        withdrawalsMap = Map.empty,
        ackKinds = Set.empty,
        artifacts = Map.empty[Hash, Artifact],
        updatedAt = FiniteDuration(10, "seconds")
      )
    } yield (state, resources)

  def facilitatorsGen: Gen[List[PeerId]] =
    Gen
      .choose(10, 100)
      .flatMap(size => Gen.containerOfN[Set, PeerId](size, arbitrary[PeerId]))
      .map(_.toList.sorted)

  def lockedStateGen(facilitators: List[PeerId]): Gen[ConsensusState[Key, Status, Outcome, Kind]] =
    for {
      key <- arbitrary[Key]
      createdAt <- arbitrary[FiniteDuration]
      facilitatorsHash <- arbitrary[Hash]
    } yield
      ConsensusState(
        key = key,
        lastOutcome = (),
        facilitators = Facilitators(facilitators),
        status = ().asLeft,
        createdAt = createdAt,
        lockStatus = LockStatus.Closed,
        spreadAckKinds = Set.empty
      )

  def acksMapGen(facilitators: List[PeerId]): Gen[Map[(PeerId, Kind), Set[PeerId]]] =
    Gen.listOfN(facilitators.size, Gen.someOf(facilitators).map(_.toSet)).map { acksSet =>
      facilitators.map(peerId => (peerId, ())).zip(acksSet).toMap
    }
}
