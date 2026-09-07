package io.constellationnetwork.node.shared.infrastructure.consensus

import java.io.IOException
import java.util.concurrent.TimeoutException

import cats.effect.IO

import scala.concurrent.duration._

import org.http4s.ember.client.EmberClientBuilder
import org.http4s.{Method, Request}
import weaver.SimpleIOSuite

/** Dependency-policy characterization only: no sockets, live peers, or simulated consensus acceptance. */
object StockGossipRetryPolicySuite extends SimpleIOSuite {
  private val policy = EmberClientBuilder.default[IO].retryPolicy

  test("stock POST does not retry the observed Broken pipe exception") {
    val request = Request[IO](method = Method.POST)
    IO.pure(expect(!request.isIdempotent) && expect(policy(request, Left(new IOException("Broken pipe")), 1).isEmpty))
  }

  test("stock GET retries Broken pipe immediately but stops after two retries") {
    val request = Request[IO](method = Method.GET)
    val error = Left(new IOException("Broken pipe"))
    IO.pure(
      expect(policy(request, error, 1).contains(0.seconds)) &&
        expect(policy(request, error, 2).contains(0.seconds)) &&
        expect(policy(request, error, 3).isEmpty)
    )
  }

  test("stock GET does not retry a generic IOException or TimeoutException") {
    val request = Request[IO](method = Method.GET)
    IO.pure(
      expect(policy(request, Left(new IOException("unclassified")), 1).isEmpty) &&
        expect(policy(request, Left(new TimeoutException("timeout")), 1).isEmpty)
    )
  }

  test("stock POST does not retry Connection reset by peer either") {
    val request = Request[IO](method = Method.POST)
    IO.pure(expect(policy(request, Left(new IOException("Connection reset by peer")), 1).isEmpty))
  }
}
