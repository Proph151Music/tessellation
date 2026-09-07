package io.constellationnetwork.node.shared.infrastructure.gossip.p2p

import java.io.IOException

import cats.effect.{IO, Ref, Resource}
import cats.syntax.all._

import scala.concurrent.duration._

import io.constellationnetwork.node.shared.config.types.GossipTimeoutsConfig
import io.constellationnetwork.node.shared.domain.cluster.services.Session
import io.constellationnetwork.node.shared.http.p2p.headers.{`X-Id`, `X-Session-Token`}
import io.constellationnetwork.node.shared.http.p2p.middlewares.PeerAuthMiddleware
import io.constellationnetwork.node.shared.infrastructure.cluster.storage.SessionStorage
import io.constellationnetwork.schema.cluster.{SessionToken, TokenValid, TokenVerificationResult}
import io.constellationnetwork.schema.gossip.{PeerRumorInquiryRequest, QueryCommonRumorsRequest}
import io.constellationnetwork.schema.peer.{P2PContext, PeerId}
import io.constellationnetwork.security.key.ops.PublicKeyOps
import io.constellationnetwork.security.{KeyPairGenerator, SecurityProvider}

import com.comcast.ip4s.{Host, Port}
import org.http4s._
import org.http4s.client.Client
import weaver.SimpleIOSuite

object GossipQueryAuthenticationSuite extends SimpleIOSuite {
  test("tampering with a retried signed query is rejected, not retried or accepted") {
    SecurityProvider.forAsync[IO].use { implicit sp =>
      for {
        keyPair <- KeyPairGenerator.makeKeyPair[IO]
        id = PeerId.fromId(keyPair.getPublic.toId)
        storage <- SessionStorage.make[IO]
        attempts <- Ref.of[IO, Int](0)
        accepted <- Ref.of[IO, Int](0)
        routes = HttpRoutes.of[IO] { case _ => accepted.update(_ + 1).as(Response[IO]()) }
        verified = PeerAuthMiddleware.requestVerifierMiddleware(routes).orNotFound
        transport = Client[IO] { req =>
          Resource.eval(attempts.updateAndGet(_ + 1).flatMap {
            case 1 => IO.raiseError[Response[IO]](new IOException("Broken pipe"))
            case _ => verified.run(req.withEntity("tampered"))
          })
        }
        signed = PeerAuthMiddleware.requestSignerMiddleware(transport, keyPair.getPrivate, storage, id)
        req = Request[IO](Method.POST, Uri.unsafeFromString("http://127.0.0.1/rumors/peer/query")).withEntity("original")
        status <- GossipQueryRetry(signed).run(req).use(response => IO.pure(response.status))
        count <- attempts.get
        acceptCount <- accepted.get
      } yield expect(status == Status.Unauthorized) && expect(count == 2) && expect(acceptCount == 0)
    }
  }

  test("both attempts are signed with the real middleware and pass real signature verification") {
    SecurityProvider.forAsync[IO].use { implicit sp =>
      for {
        keyPair <- KeyPairGenerator.makeKeyPair[IO]
        id = PeerId.fromId(keyPair.getPublic.toId)
        storage <- SessionStorage.make[IO]
        token <- storage.createToken
        observed <- Ref.of[IO, Vector[(Status, String, Boolean)]](Vector.empty)
        routes = HttpRoutes.of[IO] { case req => IO.pure(Response[IO]().withBodyStream(req.body)) }
        verified = PeerAuthMiddleware.requestVerifierMiddleware(routes).orNotFound
        transport = Client[IO] { req =>
          Resource.eval {
            for {
              response <- verified.run(req)
              body <- response.as[String]
              count <- observed.modify { rows =>
                (rows :+ ((response.status, body, req.headers.get[`X-Session-Token`].exists(_.token == token))), rows.size)
              }
              result <- if (count == 0) IO.raiseError[Response[IO]](new IOException("Broken pipe"))
              else IO.pure(Response[IO]().withEntity(body))
            } yield result
          }
        }
        signed = PeerAuthMiddleware.requestSignerMiddleware(transport, keyPair.getPrivate, storage, id)
        request = Request[IO](Method.POST, Uri.unsafeFromString("http://127.0.0.1/rumors/peer/query")).withEntity("{\"ordinals\":{}}")
        response <- GossipQueryRetry(signed).expect[String](request)
        attempts <- observed.get
      } yield expect(response == "{\"ordinals\":{}}") &&
        expect(attempts == Vector.fill(2)((Status.Ok, "{\"ordinals\":{}}", true)))
    }
  }

  test("real GossipClient wires the retry into all three POSTs and still verifies response tokens") {
    SecurityProvider.forAsync[IO].use { implicit sp =>
      for {
        keyPair <- KeyPairGenerator.makeKeyPair[IO]
        id = PeerId.fromId(keyPair.getPublic.toId)
        checks <- Ref.of[IO, Int](0)
        calls <- Ref.of[IO, Map[String, Int]](Map.empty)
        session = new Session[IO] {
          def createSession: IO[SessionToken] = IO.raiseError(new IllegalStateException("not used"))
          def verifyToken(peer: PeerId, headerToken: Option[SessionToken]): IO[TokenVerificationResult] =
            checks.update(_ + 1).as(TokenValid)
        }
        transport = Client[IO] { req =>
          Resource.eval {
            calls.modify { seen =>
              val path = req.uri.path.renderString
              val n = seen.getOrElse(path, 0)
              (seen.updated(path, n + 1), n)
            }.flatMap {
              case 0 => IO.raiseError[Response[IO]](new IOException("Broken pipe"))
              case _ => IO.pure(Response[IO]().putHeaders(`X-Id`(id)))
            }
          }
        }
        gossip = GossipClient.make(transport, session, GossipTimeoutsConfig(1.second, 1.second))
        context = P2PContext(Host.fromString("127.0.0.1").get, Port.fromInt(9001).get, id)
        _ <- gossip.queryPeerRumors(PeerRumorInquiryRequest(Map.empty)).run(context).compile.drain
        _ <- gossip.getInitialPeerRumors.run(context).compile.drain
        _ <- gossip.queryCommonRumors(QueryCommonRumorsRequest(Set.empty)).run(context).compile.drain
        attempts <- calls.get
        verifications <- checks.get
      } yield expect(attempts == Map("/rumors/peer/query" -> 2, "/rumors/peer/init" -> 2, "/rumors/common/query" -> 2)) &&
        expect(verifications == 3)
    }
  }
}
