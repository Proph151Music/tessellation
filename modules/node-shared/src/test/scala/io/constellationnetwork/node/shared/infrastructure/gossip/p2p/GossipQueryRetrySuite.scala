package io.constellationnetwork.node.shared.infrastructure.gossip.p2p

import java.io.IOException
import java.util.concurrent.TimeoutException

import cats.effect.testkit.TestControl
import cats.effect.{IO, Ref, Resource}
import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.http.p2p.middlewares.TimeoutMiddleware.withTimeout

import fs2.Stream
import org.http4s._
import org.http4s.client.Client
import org.http4s.ember.client.EmberClientBuilder
import org.http4s.headers.`Idempotency-Key`
import weaver.SimpleIOSuite

object GossipQueryRetrySuite extends SimpleIOSuite {
  private def request(path: String = "/rumors/peer/query", method: Method = Method.POST): Request[IO] =
    Request[IO](method = method, uri = Uri.unsafeFromString(s"http://127.0.0.1$path")).withEntity("{}")

  private def failing(counter: Ref[IO, Int], error: Throwable): Client[IO] = Client { _ =>
    Resource.eval(counter.update(_ + 1) >> IO.raiseError[Response[IO]](error))
  }

  test("all three read-only POST queries retry Broken pipe once with identical replayed bodies") {
    List("/rumors/peer/query", "/rumors/peer/init", "/rumors/common/query").traverse { path =>
      for {
        bodies <- Ref.of[IO, Vector[String]](Vector.empty)
        client = Client[IO] { req =>
          Resource.eval {
            req.as[String].flatMap(body => bodies.modify(rows => (rows :+ body, rows.size))).flatMap {
              case 0 => IO.raiseError[Response[IO]](new IOException("Broken pipe"))
              case _ => IO.pure(Response[IO]().withEntity("ok"))
            }
          }
        }
        response <- GossipQueryRetry(client).expect[String](request(path))
        seen <- bodies.get
      } yield expect(response == "ok") && expect(seen == Vector("{}", "{}"))
    }.map(_.reduce(_ && _))
  }

  test("persistent disconnects escape after exactly two attempts") {
    List[Throwable](new IOException("Broken pipe"), new IOException("Connection reset by peer"), new fs2.io.ClosedChannelException())
      .traverse { error =>
        for {
          counter <- Ref.of[IO, Int](0)
          result <- GossipQueryRetry(failing(counter, error)).expect[String](request()).attempt
          attempts <- counter.get
        } yield expect(result == Left(error)) && expect(attempts == 2)
      }
      .map(_.reduce(_ && _))
  }

  test("GETs, mutations, and similarly named paths receive no added retry") {
    List(
      request("/rumors/common/offer", Method.GET),
      request("/rumors/peer/query", Method.GET),
      request("/cluster/join"),
      request("/rumors/peer/query/extra"),
      request("/rumors/peer/query", Method.PUT)
    ).traverse { req =>
      for {
        counter <- Ref.of[IO, Int](0)
        result <- GossipQueryRetry(failing(counter, new IOException("Broken pipe"))).expect[String](req).attempt
        attempts <- counter.get
      } yield expect(result.isLeft) && expect(attempts == 1)
    }.map(_.reduce(_ && _))
  }

  test("timeouts, unknown I/O failures and validation exceptions receive no added retry") {
    List[Throwable](new TimeoutException(), new IOException("unknown"), new IOException(), new IllegalArgumentException("invalid"))
      .traverse { error =>
        for {
          counter <- Ref.of[IO, Int](0)
          result <- GossipQueryRetry(failing(counter, error)).expect[String](request()).attempt
          attempts <- counter.get
        } yield expect(result == Left(error)) && expect(attempts == 1)
      }
      .map(_.reduce(_ && _))
  }

  test("requests already eligible for built-in retries do not receive another retry layer") {
    for {
      counter <- Ref.of[IO, Int](0)
      req = request().putHeaders(`Idempotency-Key`("test-query"))
      result <- GossipQueryRetry(failing(counter, new IOException("Broken pipe"))).expect[String](req).attempt
      count <- counter.get
    } yield expect(result.isLeft) && expect(count == 1)
  }

  test("HTTP error responses including authentication failures are not retried") {
    List(Status.Unauthorized, Status.Forbidden, Status.InternalServerError).traverse { status =>
      for {
        counter <- Ref.of[IO, Int](0)
        client = Client[IO](_ => Resource.eval(counter.update(_ + 1).as(Response[IO](status))))
        response <- GossipQueryRetry(client).run(request()).use(r => IO.pure(r.status))
        attempts <- counter.get
      } yield expect(response == status) && expect(attempts == 1)
    }.map(_.reduce(_ && _))
  }

  test("a partially consumed response is never replayed and is released once") {
    for {
      attempts <- Ref.of[IO, Int](0)
      releases <- Ref.of[IO, Int](0)
      received <- Ref.of[IO, Vector[Byte]](Vector.empty)
      error = new IOException("Broken pipe")
      body = Stream.emit[IO, Byte](42) ++ Stream.raiseError[IO](error)
      client = Client[IO] { _ =>
        Resource.make(attempts.update(_ + 1).as(Response[IO]().withBodyStream(body)))(_ => releases.update(_ + 1))
      }
      result <- GossipQueryRetry(client).run(request()).use(_.body.evalMap(b => received.update(_ :+ b)).compile.drain).attempt
      count <- attempts.get
      freed <- releases.get
      bytes <- received.get
    } yield expect(result == Left(error)) && expect(count == 1) && expect(freed == 1) && expect(bytes == Vector[Byte](42))
  }

  test("failed acquisition resources are released before the retry starts") {
    for {
      events <- Ref.of[IO, Vector[String]](Vector.empty)
      attempts <- Ref.of[IO, Int](0)
      client = Client[IO] { _ =>
        Resource.eval(attempts.updateAndGet(_ + 1)).flatMap { n =>
          Resource.make(events.update(_ :+ s"acquire$n"))(_ => events.update(_ :+ s"release$n")).flatMap { _ =>
            Resource.eval(if (n == 1) IO.raiseError[Response[IO]](new IOException("Broken pipe")) else IO.pure(Response[IO]()))
          }
        }
      }
      _ <- GossipQueryRetry(client).run(request()).use(_ => IO.unit)
      seen <- events.get
    } yield expect(seen == Vector("acquire1", "release1", "acquire2", "release2"))
  }

  test("one shared acquisition deadline bounds both attempts and cancels the second") {
    TestControl.executeEmbed {
      for {
        attempts <- Ref.of[IO, Int](0)
        canceled <- Ref.of[IO, Boolean](false)
        client = Client[IO] { _ =>
          Resource.eval(attempts.updateAndGet(_ + 1).flatMap {
            case 1 => IO.sleep(40.millis) >> IO.raiseError[Response[IO]](new IOException("Broken pipe"))
            case _ => IO.never[Response[IO]].onCancel(canceled.set(true))
          })
        }
        start <- IO.monotonic
        result <- withTimeout(GossipQueryRetry(client), 50.millis).run(request()).use(_ => IO.unit).attempt
        elapsed <- IO.monotonic.map(_ - start)
        count <- attempts.get
        stopped <- canceled.get
      } yield expect(result.left.exists(_.isInstanceOf[TimeoutException])) &&
        expect(elapsed == 50.millis) && expect(count == 2) && expect(stopped)
    }
  }

  test("cancellation during the first attempt does not trigger a second") {
    TestControl.executeEmbed {
      for {
        attempts <- Ref.of[IO, Int](0)
        client = Client[IO](_ => Resource.eval(attempts.update(_ + 1) >> IO.never[Response[IO]]))
        fiber <- GossipQueryRetry(client).run(request()).use(_ => IO.unit).start
        _ <- IO.sleep(1.second)
        _ <- fiber.cancel
        count <- attempts.get
      } yield expect(count == 1)
    }
  }

  test("real loopback POST recovers from a disconnect within the same operation") {
    GossipDisconnectFixture.peer(failures = 1).use { peer =>
      EmberClientBuilder.default[IO].build.use { client =>
        for {
          response <- GossipQueryRetry(client).expect[String](request().withUri(peer.uri))
          requests <- peer.requests.get
        } yield expect(response == "ok") && expect(requests.size == 2) && expect(requests.forall(_.body == "{}"))
      }
    }.timeout(10.seconds)
  }

  test("real loopback persistent disconnect does not exceed the retry bound") {
    GossipDisconnectFixture.peer(failures = 10).use { peer =>
      EmberClientBuilder.default[IO].build.use { client =>
        for {
          result <- GossipQueryRetry(client).expect[String](request().withUri(peer.uri)).attempt
          requests <- peer.requests.get
        } yield expect(result.isLeft) && expect(requests.size == 2)
      }
    }.timeout(10.seconds)
  }
}
