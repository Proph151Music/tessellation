package io.constellationnetwork.node.shared.infrastructure.consensus

import cats.effect.std.Supervisor
import cats.effect.{Async, Clock, Temporal}
import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.config.types.ConsensusConfig
import io.constellationnetwork.node.shared.infrastructure.consensus.trigger.TimeTrigger

import org.typelevel.log4cats.slf4j.Slf4jLogger

/** Local scheduling only: triggering a round does not authorize its finalization. */
private[consensus] object ConsensusTimeTrigger {
  def shouldDetectStall[K, S, O, Kind](config: ConsensusConfig, state: ConsensusState[K, S, O, Kind]): Boolean =
    config.timeTriggerPeriod.isEmpty || state.triggerStartedAt.nonEmpty

  /** Observe a trigger only while this local round exists, and only from current facilitators. Idle observation and pre-received
    * future-round gossip are not elapsed active consensus. Once set, later gossip cannot reset these clocks.
    */
  def observeTriggers[F[_]: Async, K, S, O, A, Kind](
    state: ConsensusState[K, S, O, Kind],
    resources: ConsensusResources[A, Kind]
  ): F[ConsensusState[K, S, O, Kind]] = if (state.triggerStartedAt.nonEmpty && state.timeTriggerStartedAt.nonEmpty) state.pure[F]
  else {
    val triggers = state.facilitators.value.flatMap { peer =>
      resources.peerDeclarationsMap.get(peer).flatMap(_.facility).flatMap(_.trigger)
    }
    val start = state.triggerStartedAt.isEmpty && triggers.nonEmpty
    val startTime = state.timeTriggerStartedAt.isEmpty && triggers.contains(TimeTrigger)
    if (!start && !startTime) state.pure[F]
    else
      Clock[F].monotonic.map { now =>
        state.copy(
          triggerStartedAt = state.triggerStartedAt.orElse(Option.when(start)(now)),
          timeTriggerStartedAt = state.timeTriggerStartedAt.orElse(Option.when(startTime)(now))
        )
      }
  }

  private def cadenceStart(actualStart: Option[FiniteDuration], deadline: Option[FiniteDuration]): Option[FiniteDuration] =
    actualStart.map(start => deadline.fold(start)(_.min(start)))

  /** Capture before advancing facilities: a timed majority clears the pending timer in both GL0 and Currency L0. This anchor is local round
    * metadata and survives that cancellation without keeping an obsolete callback live or backdating recovery timestamps.
    */
  def observeTiming[F[_]: Async, K, S, O, A, Kind](
    state: ConsensusState[K, S, O, Kind],
    resources: ConsensusResources[A, Kind],
    getDeadline: F[Option[FiniteDuration]]
  ): F[ConsensusState[K, S, O, Kind]] =
    observeTriggers(state, resources).flatMap { observed =>
      if (observed.timeTriggerCadenceStartedAt.nonEmpty || observed.timeTriggerStartedAt.isEmpty) observed.pure[F]
      else
        getDeadline.map { deadline =>
          observed.copy(timeTriggerCadenceStartedAt = cadenceStart(observed.timeTriggerStartedAt, deadline))
        }
    }

  def nextDeadline(
    config: ConsensusConfig,
    now: FiniteDuration,
    previousTimedStart: Option[FiniteDuration],
    previousDeadline: Option[FiniteDuration] = None
  ): FiniteDuration =
    // A delayed callback must not permanently move this node's cadence. The
    // retained local deadline is scheduling evidence, not elapsed participation:
    // keep the actual trigger timestamps used by recovery unchanged. Bootstrap
    // has no completed timed start and must not reuse a leftover deadline.
    (config.timeTriggerPeriod, cadenceStart(previousTimedStart, previousDeadline))
      .mapN(_ + _)
      .getOrElse(now + config.timeTriggerInterval)
      .max(now)

  def schedule[F[_]: Async](
    config: ConsensusConfig,
    previousTimedStart: Option[FiniteDuration],
    setDeadline: FiniteDuration => F[Unit],
    getDeadline: F[Option[FiniteDuration]]
  )(facilitate: F[Unit])(implicit supervisor: Supervisor[F]): F[Unit] = {
    val logger = Slf4jLogger.getLoggerFromName[F]("ConsensusTimeTrigger")
    for {
      now <- Clock[F].monotonic
      deadline = nextDeadline(config, now, previousTimedStart)
      _ <- setDeadline(deadline)
      _ <- logger.debug(
        s"Scheduled timed consensus {delayMs=${(deadline - now).toMillis}, periodMs=${config.timeTriggerPeriod.map(_.toMillis)}}"
      )
      _ <- supervisor.supervise {
        (Clock[F].monotonic.flatMap(time => Temporal[F].sleep((deadline - time).max(Duration.Zero))) >>
          (getDeadline, Clock[F].monotonic).mapN { (current, time) =>
            // A superseded or cleared timer must not fire for a different deadline.
            // The existing consensus-state creation guard still arbitrates concurrent triggers.
            current.contains(deadline) && time >= deadline
          }.ifM(facilitate, Temporal[F].unit))
          .handleErrorWith(logger.error(_)("Error triggering consensus with time trigger"))
      }
    } yield ()
  }
}
