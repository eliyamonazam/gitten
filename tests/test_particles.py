from gitten.particles import ParticleSystem


def test_new_system_has_no_particles():
    ps = ParticleSystem()
    assert ps.positions(now=0.0) == []


def test_spawn_adds_a_particle_at_full_opacity():
    ps = ParticleSystem()
    ps.spawn_particle(10.0, 20.0, now=0.0, lifespan=1.0)
    positions = ps.positions(now=0.0)
    assert len(positions) == 1
    x, y, opacity = positions[0]
    assert x == 10.0
    assert y == 20.0
    assert opacity == 1.0


def test_opacity_fades_linearly_to_zero():
    ps = ParticleSystem()
    ps.spawn_particle(0.0, 0.0, now=0.0, lifespan=1.0)
    _, _, opacity_half = ps.positions(now=0.5)[0]
    assert abs(opacity_half - 0.5) < 1e-9


def test_update_and_prune_drops_expired_particles():
    ps = ParticleSystem()
    ps.spawn_particle(0.0, 0.0, now=0.0, lifespan=0.5)
    ps.update_and_prune(now=1.0)
    assert ps.positions(now=1.0) == []


def test_update_and_prune_keeps_still_alive_particles():
    ps = ParticleSystem()
    ps.spawn_particle(0.0, 0.0, now=0.0, lifespan=1.0)
    ps.update_and_prune(now=0.5)
    assert len(ps.positions(now=0.5)) == 1


def test_drift_moves_the_particle_over_time():
    ps = ParticleSystem()
    ps.spawn_particle(0.0, 0.0, now=0.0, lifespan=1.0, dx=10.0, dy=-5.0)
    x, y, _ = ps.positions(now=0.5)[0]
    assert x == 5.0
    assert y == -2.5


def test_multiple_particles_tracked_independently():
    ps = ParticleSystem()
    ps.spawn_particle(0.0, 0.0, now=0.0, lifespan=1.0)
    ps.spawn_particle(100.0, 100.0, now=0.2, lifespan=1.0)
    ps.update_and_prune(now=0.9)
    positions = ps.positions(now=0.9)
    # first particle (age 0.9/1.0) has nearly expired but is still alive;
    # second (age 0.7/1.0) is well within its lifespan.
    assert len(positions) == 2
