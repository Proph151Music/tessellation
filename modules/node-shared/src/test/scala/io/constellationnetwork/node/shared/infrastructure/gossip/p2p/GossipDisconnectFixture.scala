package io.constellationnetwork.node.shared.infrastructure.gossip.p2p

import java.io.{BufferedReader, InputStreamReader}
import java.net._
import java.nio.charset.StandardCharsets

import cats.effect.{IO, Ref, Resource}
import cats.syntax.all._

import org.http4s.Uri

/** Loopback-only HTTP peer. Fully reads a small request, then closes without a response for the requested number of attempts. */
object GossipDisconnectFixture {
  final case class Observation(requestLine: String, body: String)
  final case class Peer(uri: Uri, requests: Ref[IO, Vector[Observation]])

  def peer(failures: Int): Resource[IO, Peer] =
    for {
      server <- Resource.make(IO.blocking {
        val socket = new ServerSocket(0, 8, InetAddress.getByName("127.0.0.1"))
        socket.setSoTimeout(250)
        socket
      })(socket => IO.blocking(socket.close()))
      requests <- Resource.eval(Ref.of[IO, Vector[Observation]](Vector.empty))
      _ <- loop(server, requests, failures).background
    } yield Peer(Uri.unsafeFromString(s"http://127.0.0.1:${server.getLocalPort}/rumors/peer/query"), requests)

  private def loop(server: ServerSocket, requests: Ref[IO, Vector[Observation]], failures: Int): IO[Unit] =
    IO.blocking(server.accept()).attempt.flatMap {
      case Left(_: SocketTimeoutException) => IO.unit
      case Left(error)                     => IO.raiseError(error)
      case Right(socket) =>
        Resource.make(IO.pure(socket))(s => IO.blocking(s.close())).use { s =>
          for {
            observation <- IO.blocking(readRequest(s))
            attempt <- requests.modify(rows => (rows :+ observation, rows.size + 1))
            _ <- IO.blocking {
              if (attempt > failures) {
                s.getOutputStream.write(
                  "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok".getBytes(StandardCharsets.US_ASCII)
                )
                s.getOutputStream.flush()
              }
            }
          } yield ()
        }
    } >> IO.defer(loop(server, requests, failures))

  private def readRequest(socket: Socket): Observation = {
    socket.setSoTimeout(2000)
    val reader = new BufferedReader(new InputStreamReader(socket.getInputStream, StandardCharsets.ISO_8859_1))
    val requestLine = Option(reader.readLine()).getOrElse(throw new IllegalStateException("missing request"))
    var header = reader.readLine()
    var length = 0
    var headerBytes = requestLine.length
    while (header != null && header.nonEmpty && headerBytes < 16384) {
      headerBytes += header.length
      if (header.toLowerCase(java.util.Locale.ROOT).startsWith("content-length:"))
        length = header.split(":", 2)(1).trim.toInt
      require(!header.toLowerCase(java.util.Locale.ROOT).startsWith("transfer-encoding:"), "fixture requires fixed-length entity")
      header = reader.readLine()
    }
    require(header != null && header.isEmpty && headerBytes < 16384, "invalid/oversized headers")
    require(length >= 0 && length <= 4096, "oversized test entity")
    val body = new Array[Char](length)
    var offset = 0
    while (offset < length) {
      val read = reader.read(body, offset, length - offset)
      require(read > 0, "truncated request")
      offset += read
    }
    Observation(requestLine, new String(body))
  }
}
