package io.constellationnetwork.node.shared.infrastructure.gossip.p2p

import java.io.IOException

import cats.effect.Async

import scala.concurrent.duration._

import org.http4s.Method.POST
import org.http4s.client.Client
import org.http4s.client.middleware.Retry

/** One additional acquisition attempt for replayable, read-only gossip queries. Keep the existing timeout outside this client. */
private[p2p] object GossipQueryRetry {
  private val queryPaths = Set("/rumors/peer/query", "/rumors/peer/init", "/rumors/common/query")

  def apply[F[_]: Async](client: Client[F]): Client[F] = {
    // The library middleware releases the failed acquisition before starting the next.
    // Re-enter the signed client, never replay a consumed response stream.
    val retryClient = Retry.create[F](
      (_, result, attempt) =>
        result match {
          case Left(error) if attempt == 1 && isDisconnect(error) => Some(Duration.Zero)
          case _                                                  => None
        },
      logRetries = false
    )(client)

    Client { request =>
      if (request.method == POST && !request.isIdempotent && queryPaths.contains(request.uri.path.renderString))
        retryClient.run(request)
      else client.run(request)
    }
  }

  private def isDisconnect(error: Throwable): Boolean = error match {
    case _: fs2.io.ClosedChannelException => true
    case error: IOException               => Set("Broken pipe", "Connection reset by peer").contains(error.getMessage)
    case _                                => false
  }
}
