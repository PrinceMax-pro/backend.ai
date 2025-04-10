python_sources(
    name="src",
    dependencies=[
        "src/ai/backend/wsproxy/cli:src",  # not auto-inferred (due to lazy-loading cmdgroup)
        "src/ai/backend/wsproxy/api:src",  # not auto-inferred (due to lazy-loading cmdgroup)
        ":resources",
    ],
)

visibility_private_component(
    allowed_dependents=[
        "//src/ai/backend/testutils/**",
    ],
    allowed_dependencies=[
        "//src/ai/backend/**",
        "!//src/ai/backend/web/**",
        "!//src/ai/backend/account_manager/**",
        "!//src/ai/backend/manager/**",
        "!//src/ai/backend/agent/**",
        "!//src/ai/backend/storage/**",
        "!//src/ai/backend/client/**",
    ],
)

python_distribution(
    name="dist",
    dependencies=[
        ":src",
        "!!stubs/trafaret:stubs",
    ],
    provides=python_artifact(
        name="backend.ai-wsproxy",
        description="Backend.AI WSProxy",
        license="LGPLv3",
    ),
    entry_points={
        "backendai_cli_v10": {
            "wsproxy": "ai.backend.wsproxy.cli.__main__:main",
            "wsproxy.start-server": "ai.backend.wsproxy.server:main",
        },
    },
    generate_setup=True,
    tags=["wheel"],
)

pex_binary(
    name="backendai-wsproxy",
    **common_scie_config("lazy"),
    dependencies=[
        ":src",
        ":buildscript",
        "!!stubs/trafaret:stubs",
    ],
)

pex_binary(
    name="backendai-wsproxy-fat",
    **common_scie_config("eager"),
    dependencies=[
        ":src",
        ":buildscript",
        "!!stubs/trafaret:stubs",
    ],
)

run_shell_command(
    name="checksum",
    command=(
        "find . -name 'backendai-wsproxy*' -not -name '*.sha256' | xargs -I {} sh -c"
        " 'sha256sum {} > {}.sha256'"
    ),
    workdir="/dist",
    execution_dependencies=[
        ":backendai-wsproxy",
        ":backendai-wsproxy-fat",
    ],
    tags=["checksum"],
)

resource(name="version", source="VERSION")
resource(name="buildscript", source="BUILD")
resources(
    name="resources",
    dependencies=[
        ":version",
    ],
    sources=["**/py.typed", "templates/**"],
)
