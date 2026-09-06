package io.constellationnetwork.node.shared.infrastructure.consensus

import cats.effect.std.Supervisor
import cats.effect.testkit.TestControl
import cats.effect.{IO, Ref}
import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.config.types.{ConsensusConfig, EventCutterConfig}

import eu.timepit.refined.auto._
import eu.timepit.refined.pureconfig._
import pureconfig.ConfigSource
import pureconfig.generic.auto._
import weaver.SimpleIOSuite

object ConsensusTimeTriggerSuite extends SimpleIOSuite {
  private val legacy = ConsensusConfig(43.seconds, 50.seconds, 3L, 10.seconds, 10.seconds, EventCutterConfig(1024, 100))
  private val periodic = legacy.copy(timeTriggerPeriod = Some(65.seconds))

  private val configuration = """
    time-trigger-interval = 43 seconds
    declaration-timeout = 50 seconds
    declaration-range-limit = 3
    lock-duration = 10 seconds
    peers-declaration-timeout = 10 seconds
    event-cutter { max-binary-size-bytes = 1024, max-update-node-parameters-size = 100 }
  """

  test("existing configuration without the new field still loads with legacy behavior") {
    IO.pure(expect.same(ConfigSource.string(configuration).load[ConsensusConfig], Right(legacy)))
  }

  test("explicitly disabled and enabled configurations load correctly") {
    IO.pure(
      expect.same(ConfigSource.string(configuration + "\ntime-trigger-period = null").load[ConsensusConfig], Right(legacy)) &&
        expect.same(ConfigSource.string(configuration + "\ntime-trigger-period = 65 seconds").load[ConsensusConfig], Right(periodic))
    )
  }

  test("disabled mode preserves the full post-completion delay") {
    IO.pure(expect.same(ConsensusTimeTrigger.nextDeadline(legacy, 35.seconds, Some(Duration.Zero)), 78.seconds))
  }

  test("enabled mode includes consensus work in the selected period") {
    IO.pure(expect.same(ConsensusTimeTrigger.nextDeadline(periodic, 35.seconds, Some(Duration.Zero)), 65.seconds))
  }

  test("a fast round does not run faster than the selected period") {
    IO.pure(expect.same(ConsensusTimeTrigger.nextDeadline(periodic, 10.seconds, Some(Duration.Zero)), 65.seconds))
  }

  test("an overrun requests one next round, without replaying missed epochs") {
    IO.pure(
      expect.same(ConsensusTimeTrigger.nextDeadline(periodic, 200.seconds, Some(Duration.Zero)), 200.seconds) &&
        expect.same(ConsensusTimeTrigger.nextDeadline(periodic, 210.seconds, Some(200.seconds)), 265.seconds)
    )
  }

  test("bootstrap retains the legacy initial delay when no round start is available") {
    IO.pure(expect.same(ConsensusTimeTrigger.nextDeadline(periodic, 100.seconds, None), 143.seconds))
  }

  test("zero and negative periods are rejected") {
    List(Duration.Zero, (-1).second).traverse { period =>
      IO(legacy.copy(timeTriggerPeriod = Some(period))).attempt.map(result => expect(result.isLeft))
    }.map(_.reduce(_ && _))
  }

  private def withTimer(test: (Option[FiniteDuration] => IO[Unit], Ref[IO, Option[FiniteDuration]], Ref[IO, List[FiniteDuration]]) => IO[weaver.Expectations]) =
    TestControl.executeEmbed {
      Supervisor[IO].use { implicit supervisor =>
        for {
          deadline <- Ref.of[IO, Option[FiniteDuration]](None)
          fired <- Ref.of[IO, List[FiniteDuration]](Nil)
          schedule = (startedAt: Option[FiniteDuration]) =>
            ConsensusTimeTrigger.schedule[IO](periodic, startedAt, t => deadline.set(Some(t)), deadline.get)(
              IO.monotonic.flatMap(t => fired.update(_ :+ t))
            )
          result <- test(schedule, deadline, fired)
        } yield result
      }
    }

  test("the real timer waits only for the remaining period") {
    withTimer { (schedule, _, fired) =>
      for {
        _ <- IO.sleep(35.seconds)
        _ <- schedule(Some(Duration.Zero))
        _ <- IO.sleep(29.seconds)
        before <- fired.get
        _ <- IO.sleep(2.seconds)
        after <- fired.get
      } yield expect(before.isEmpty) && expect.same(after, List(65.seconds))
    }
  }

  test("time spent installing a deadline is not added to its remaining wait") {
    TestControl.executeEmbed {
      Supervisor[IO].use { implicit supervisor =>
        for {
          deadline <- Ref.of[IO, Option[FiniteDuration]](None)
          fired <- Ref.of[IO, List[FiniteDuration]](Nil)
          _ <- IO.sleep(35.seconds)
          _ <- ConsensusTimeTrigger.schedule[IO](
            periodic,
            Some(Duration.Zero),
            t => IO.sleep(10.seconds) >> deadline.set(Some(t)),
            deadline.get
          )(IO.monotonic.flatMap(t => fired.update(_ :+ t)))
          _ <- IO.sleep(21.seconds)
          result <- fired.get
        } yield expect.same(result, List(65.seconds))
      }
    }
  }

  test("clearing a deadline suppresses its sleeping callback") {
    withTimer { (schedule, deadline, fired) =>
      for {
        _ <- schedule(Some(Duration.Zero))
        _ <- IO.sleep(10.seconds)
        _ <- deadline.set(None)
        _ <- IO.sleep(60.seconds)
        result <- fired.get
      } yield expect(result.isEmpty)
    }
  }

  test("a replaced deadline is not fired by the older callback") {
    withTimer { (schedule, _, fired) =>
      for {
        _ <- schedule(Some(Duration.Zero))
        _ <- IO.sleep(10.seconds)
        _ <- schedule(Some(10.seconds))
        _ <- IO.sleep(56.seconds)
        before <- fired.get
        _ <- IO.sleep(10.seconds)
        after <- fired.get
      } yield expect(before.isEmpty) && expect.same(after, List(75.seconds))
    }
  }

  test("an overdue timer fires once and does not create a catch-up loop") {
    withTimer { (schedule, _, fired) =>
      for {
        _ <- IO.sleep(200.seconds)
        _ <- schedule(Some(Duration.Zero))
        _ <- IO.sleep(200.seconds)
        result <- fired.get
      } yield expect.same(result, List(200.seconds))
    }
  }
}
