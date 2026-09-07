package io.constellationnetwork.node.shared.infrastructure.gossip.p2p

import cats.effect.IO

import scala.concurrent.duration._

import org.http4s.ember.client.EmberClientBuilder
import org.http4s.{Method, Request}
import weaver.SimpleIOSuite

object StockGossipDisconnectSuite extends SimpleIOSuite {
  test("stock POST fails after one loopback disconnect although the next request can succeed") {
    GossipDisconnectFixture
      .peer(failures = 1)
      .use { peer =>
        EmberClientBuilder.default[IO].build.use { client =>
          val request = Request[IO](method = Method.POST, uri = peer.uri).withEntity("{}")
          for {
            first <- client.expect[String](request).attempt
            afterFailure <- peer.requests.get
            second <- client.expect[String](request)
            all <- peer.requests.get
          } yield
            expect(first.left.exists(_.isInstanceOf[fs2.io.ClosedChannelException])) &&
              expect(afterFailure.size == 1) && expect(second == "ok") &&
              expect(all.size == 2) && expect(all.forall(_.body == "{}"))
        }
      }
      .timeout(10.seconds)
  }

  test("stock GET recovers automatically from the same loopback disconnect") {
    GossipDisconnectFixture
      .peer(failures = 1)
      .use { peer =>
        EmberClientBuilder.default[IO].build.use { client =>
          for {
            response <- client.expect[String](Request[IO](method = Method.GET, uri = peer.uri))
            requests <- peer.requests.get
          } yield expect(response == "ok") && expect(requests.size == 2)
        }
      }
      .timeout(10.seconds)
  }
}
