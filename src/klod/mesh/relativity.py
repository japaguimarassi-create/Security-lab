from __future__ import annotations

import hashlib
import unicodedata

RELATIVITY_CORPUS_VERSION = "GR-CANONICAL-CORE-1.0.0"

RELATIVITY_CANONICAL_TEXT = r"""
GENERAL RELATIVITY CANONICAL CRYPTOGRAPHIC CORPUS
Version: GR-CANONICAL-CORE-1.0.0
Convention: four-dimensional spacetime; metric signature (-,+,+,+);
Riemann convention R^rho_(sigma mu nu) =
d_mu Gamma^rho_(nu sigma) - d_nu Gamma^rho_(mu sigma)
+ Gamma^rho_(mu alpha) Gamma^alpha_(nu sigma)
- Gamma^rho_(nu alpha) Gamma^alpha_(mu sigma);
u^mu u_mu = -c^2; x^0 = c t; repeated upper/lower indices are summed.
This is a finite, canonical reference of the standard mathematical core,
not a claim that every possible exact solution or research result is finite.

1. SPACETIME AND METRIC
M is a smooth, connected, four-dimensional manifold. g is a smooth,
non-degenerate Lorentzian metric with signature (-,+,+,+).
ds^2 = g_(mu nu) dx^mu dx^nu.
g_(mu alpha) g^(alpha nu) = delta_mu^nu.
The metric volume element is dV_g = sqrt(-det(g_mu nu)) d^4 x.
A coordinate transformation x -> x' transforms g as a covariant rank-two tensor.

2. LEVI-CIVITA CONNECTION AND COVARIANT DIFFERENTIATION
The unique torsion-free, metric-compatible connection satisfies
nabla_alpha g_(mu nu) = 0 and Gamma^rho_(mu nu) = Gamma^rho_(nu mu).
Gamma^rho_(mu nu) = (1/2) g^(rho sigma) [
partial_mu g_(sigma nu) + partial_nu g_(sigma mu)
- partial_sigma g_(mu nu)].
For a scalar f: nabla_mu f = partial_mu f.
For a vector V^nu: nabla_mu V^nu = partial_mu V^nu + Gamma^nu_(mu lambda) V^lambda.
For a covector w_nu: nabla_mu w_nu = partial_mu w_nu - Gamma^lambda_(mu nu) w_lambda.
For a general tensor, add one positive connection term for each contravariant index
and one negative connection term for each covariant index.
The Lie derivative along X is L_X T; for the metric,
(L_X g)_(mu nu) = nabla_mu X_nu + nabla_nu X_mu.

3. CURVATURE
R^rho_(sigma mu nu) = partial_mu Gamma^rho_(nu sigma)
- partial_nu Gamma^rho_(mu sigma)
+ Gamma^rho_(mu lambda) Gamma^lambda_(nu sigma)
- Gamma^rho_(nu lambda) Gamma^lambda_(mu sigma).
R_(sigma nu) = R^rho_(sigma rho nu).
R = g^(mu nu) R_(mu nu).
G_(mu nu) = R_(mu nu) - (1/2) R g_(mu nu).
R_(rho sigma mu nu) = g_(rho alpha) R^alpha_(sigma mu nu).
For the Levi-Civita connection:
R_(rho sigma mu nu) = -R_(sigma rho mu nu)
= -R_(rho sigma nu mu) = R_(mu nu rho sigma).
R_(rho sigma mu nu) + R_(rho mu nu sigma) + R_(rho nu sigma mu) = 0.
The differential Bianchi identity is
nabla_lambda R^rho_(sigma mu nu)
+ nabla_mu R^rho_(sigma nu lambda)
+ nabla_nu R^rho_(sigma lambda mu) = 0.
Contracted Bianchi identity: nabla_mu G^(mu nu) = 0.

4. EINSTEIN FIELD EQUATIONS AND ACTION
G_(mu nu) + Lambda g_(mu nu) = (8 pi G_N / c^4) T_(mu nu).
Equivalently:
R_(mu nu) - (1/2) R g_(mu nu) + Lambda g_(mu nu)
= (8 pi G_N / c^4) T_(mu nu).
The trace-reversed form in four dimensions is
R_(mu nu) = (8 pi G_N / c^4) [T_(mu nu) - (1/2) T g_(mu nu)]
+ Lambda g_(mu nu), where T = g^(alpha beta) T_(alpha beta).
Einstein-Hilbert action:
S = (c^3 / (16 pi G_N)) integral_M (R - 2 Lambda) sqrt(-g) d^4 x
+ S_matter[g, matter].
T_(mu nu) = (-2 c / sqrt(-g)) delta S_matter / delta g^(mu nu)
for the stated x^0 = c t convention.
Stationarity delta S / delta g^(mu nu) = 0 gives the field equations,
with the required boundary term for a well-posed metric variation.
Stress-energy conservation follows:
nabla_mu T^(mu nu) = 0.

5. MATTER MODELS
A perfect fluid has
T_(mu nu) = (rho c^2 + p) u_mu u_nu / c^2 + p g_(mu nu),
u^mu u_mu = -c^2.
For dust p = 0. For vacuum energy T_(mu nu) = -rho_vac c^2 g_(mu nu)
under the corresponding energy-density convention.
A minimally coupled real scalar field phi with potential V(phi) has
T_(mu nu) = partial_mu phi partial_nu phi
- g_(mu nu) [(1/2) g^(alpha beta) partial_alpha phi partial_beta phi + V(phi)].
Maxwell electrodynamics in curved spacetime:
nabla_mu F^(mu nu) = mu_0 J^nu,
nabla_[alpha F_(mu nu)] = 0,
T_(mu nu) = (1/mu_0) [F_(mu alpha) F_nu^alpha
- (1/4) g_(mu nu) F_(alpha beta) F^(alpha beta)].

6. GEODESICS AND GEODESIC DEVIATION
For an affinely parameterized geodesic x^mu(lambda):
d^2 x^rho / d lambda^2
+ Gamma^rho_(mu nu) (dx^mu/dlambda) (dx^nu/dlambda) = 0.
For proper time tau, u^mu = dx^mu/dtau and u^mu u_mu = -c^2.
The geodesic equation is u^nu nabla_nu u^mu = 0.
For a connecting vector xi^mu between neighboring geodesics, with the
curvature convention declared above:
D^2 xi^mu / D tau^2 = R^mu_(nu alpha beta) u^nu u^alpha xi^beta.
The equation determines relative tidal acceleration.

7. WEAK FIELD AND LINEARIZED GRAVITY
g_(mu nu) = eta_(mu nu) + h_(mu nu), with |h_(mu nu)| << 1.
h = eta^(mu nu) h_(mu nu).
bar_h_(mu nu) = h_(mu nu) - (1/2) eta_(mu nu) h.
Lorenz gauge: partial_mu bar_h^(mu nu) = 0.
Box bar_h_(mu nu) = -(16 pi G_N / c^4) T_(mu nu).
In vacuum, Box bar_h_(mu nu) = 0.
In the transverse-traceless gauge, propagating vacuum waves have
h_TT trace zero and partial_i h_TT^(ij) = 0.
The Newtonian limit gives g_00 approximately -(1 + 2 Phi/c^2)
and nabla^2 Phi = 4 pi G_N rho.
For a source with slow motion, the leading quadrupole luminosity is
P = (G_N / (5 c^5)) < d^3 Q_ij/dt^3 d^3 Q_ij/dt^3 >,
with Q_ij the symmetric trace-free mass quadrupole.

8. SCHWARZSCHILD SOLUTION
For a static, spherically symmetric vacuum exterior with mass M:
ds^2 = -(1 - r_s/r) c^2 dt^2
+ (1 - r_s/r)^(-1) dr^2 + r^2 dOmega^2,
r_s = 2 G_N M / c^2,
dOmega^2 = dtheta^2 + sin(theta)^2 dphi^2.
The Schwarzschild horizon is at r = r_s in these coordinates.
The vacuum exterior satisfies R_(mu nu) = 0 when Lambda = 0.

9. KERR SOLUTION
For an uncharged rotating vacuum black hole with mass M and
a = J/(M c), define Sigma = r^2 + a^2 cos^2(theta),
Delta = r^2 - (2 G_N M/c^2) r + a^2.
In Boyer-Lindquist coordinates:
ds^2 = -(1 - 2 G_N M r/(c^2 Sigma)) c^2 dt^2
- (4 G_N M a r sin^2(theta)/(c Sigma)) c dt dphi
+ (Sigma/Delta) dr^2 + Sigma dtheta^2
+ [r^2 + a^2 + (2 G_N M a^2 r sin^2(theta))/(c^2 Sigma)]
sin^2(theta) dphi^2.
The outer horizon is r_+ = G_N M/c^2 + sqrt((G_N M/c^2)^2 - a^2).

10. REISSNER-NORDSTROM SOLUTION
For a non-rotating charged mass, in SI units:
f(r) = 1 - 2 G_N M/(c^2 r) + G_N Q^2/(4 pi epsilon_0 c^4 r^2).
ds^2 = -f(r)c^2dt^2 + f(r)^(-1)dr^2 + r^2 dOmega^2.
The horizons are roots of f(r) = 0 when real.

11. HOMOGENEOUS AND ISOTROPIC COSMOLOGY
The FLRW metric is
ds^2 = -c^2 dt^2 + a(t)^2 [
dr^2/(1-k r^2) + r^2 dOmega^2].
H = dot(a)/a.
H^2 = (8 pi G_N/3) rho - k c^2/a^2 + Lambda c^2/3.
ddot(a)/a = -(4 pi G_N/3)(rho + 3p/c^2) + Lambda c^2/3.
dot(rho) + 3 H (rho + p/c^2) = 0.
For a spatially flat universe, k = 0.

12. ADM 3+1 FORMULATION
The spacetime metric is
ds^2 = -alpha^2 c^2 dt^2
+ gamma_ij (dx^i + beta^i dt)(dx^j + beta^j dt),
where alpha is lapse, beta^i is shift and gamma_ij is the induced spatial metric.
With K_ij = -(1/(2 alpha c)) (partial_t gamma_ij - D_i beta_j - D_j beta_i)
for this sign convention, the Hamiltonian constraint is
^(3)R + K^2 - K_ij K^ij = 16 pi G_N E/c^4 + 2 Lambda,
and the momentum constraint is
D_j(K^(ij) - gamma^(ij) K) = 8 pi G_N S^i/c^4.
Here E and S^i are the energy and momentum densities measured by the unit normal.

13. TOLMAN-OPPENHEIMER-VOLKOFF EQUILIBRIUM
For a static, spherically symmetric perfect-fluid star:
dm/dr = 4 pi r^2 rho,
dp/dr = - G_N (rho + p/c^2)
(m + 4 pi r^3 p/c^2) /
[r^2 (1 - 2 G_N m/(c^2 r))].
An equation of state p = p(rho) closes the system.

14. COSMOLOGICAL CONSTANT AND VACUUM
Lambda has dimensions of inverse length squared. A positive Lambda produces
a de Sitter vacuum solution with R_(mu nu) = Lambda g_(mu nu)
and R = 4 Lambda in four dimensions. An anti-de Sitter vacuum has
negative Lambda. The cosmological constant may be moved to the matter side
as vacuum stress-energy only with a consistent sign and units.

15. SYMMETRIES AND CONSERVATION
A Killing vector xi satisfies nabla_mu xi_nu + nabla_nu xi_mu = 0.
For a geodesic with tangent u, the scalar xi_mu u^mu is conserved.
Spacetime isometries generate conserved quantities along geodesics.
Noether's theorem connects continuous symmetries of the action to conserved
currents, subject to the equations of motion and boundary conditions.

16. DIMENSIONAL AND COVARIANCE REQUIREMENTS
All tensor equations are coordinate-covariant. Indices are raised and lowered
only with g and its inverse. Geometric identities hold independently of
coordinates. Constants G_N, c, epsilon_0 and mu_0 retain their declared SI
meaning. Coordinate components are not invariant observables by themselves.
The field equations, matter equations, initial data and boundary conditions
must be mutually consistent.
"""

def canonical_relativity_bytes() -> bytes:
    normalized = unicodedata.normalize("NFC", RELATIVITY_CANONICAL_TEXT)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.strip().split("\n"))
    return (RELATIVITY_CORPUS_VERSION + "\n" + normalized + "\n").encode("utf-8")


def relativity_digest() -> bytes:
    return hashlib.sha256(canonical_relativity_bytes()).digest()


def relativity_fingerprint() -> str:
    return relativity_digest().hex()


def verify_relativity_corpus(expected_sha256: str) -> bool:
    if len(expected_sha256) != 64:
        return False
    try:
        expected = bytes.fromhex(expected_sha256)
    except ValueError:
        return False
    return hashlib.sha256(canonical_relativity_bytes()).digest() == expected
