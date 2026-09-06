package io.constellationnetwork.node.shared.infrastructure.consensus

import cats.effect.std.Supervisor
import cats.effect.{Async, Clock, Temporal}
import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.config.types.ConsensusConfig

import org.typelevel.log4cats.slf4j.Slf4jLogger

/** Local scheduling only: triggering a round does not authorize its finalization. */
private[consensus] object ConsensusTimeTrigger {
  def nextDeadline(config: ConsensusConfig, now: FiniteDuration, previousRoundStartedAt: Option[FiniteDuration]): FiniteDuration =
    (config.timeTriggerPeriod, previousRoundStartedAt)
      .mapN(_ + _)
      .getOrElse(now + config.timeTriggerInterval)
      .max(now)

  def schedule[F[_]: Async](
    config: ConsensusConfig,
    previousRoundStartedAt: Option[FiniteDuration],
    setDeadline: FiniteDuration => F[Unit],
    getDeadline: F[Option[FiniteDuration]]
  )(facilitate: F[Unit])(implicit supervisor: Supervisor[F]): F[Unit] = {
    val logger = Slf4jLogger.getLoggerFromName[F]("ConsensusTimeTrigger")
    for {
      now <- Clock[F].monotonic
      deadline = nextDeadline(config, now, previousRoundStartedAt)
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
