"""Runtime configuration: env-var defaults, config.json overlay, and
pydantic validation.

Precedence (lowest to highest): hard-coded env-var defaults set in
``Config.__init__`` -> values loaded from ``config.json`` (or the file
named by ``CONFIG_FILE``) -> mode-specific overrides applied later via
``Config.apply_mode_config()``.
"""

import json
import logging
import os

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.config.mode_profiles import MODE_CONFIGS

logger = logging.getLogger(__name__)


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


class ConfigSchema(BaseModel):
    """Validated shape of runtime configuration, with field-level constraints.

    Used by ``Config.validate()`` to check and normalize the values
    accumulated on a ``Config`` instance from env vars, ``config.json``,
    and mode overrides. ``extra="allow"`` so unrecognized keys (e.g.
    future mode-only settings) pass through rather than failing.
    """

    model_config = ConfigDict(extra="allow")

    retriever: str = "tavily"
    embedding_provider: str = "openai"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    token_limit: int = Field(default=4000, gt=0, le=12001)
    browse_chunk_max_length: int = Field(default=8192, gt=0)
    similarity_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    chunk_size: int = Field(default=500, gt=0)
    chunk_overlap: int = Field(default=100, ge=0)
    summary_token_limit: int = Field(default=1000, gt=0)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    user_agent: str
    max_search_results_per_query: int = Field(default=8, gt=0)
    memory_backend: str = "local"
    total_words: int = Field(default=1500, gt=0)
    report_format: str = "APA"
    max_iterations: int = Field(default=4, ge=0)
    agent_role: str | None = None
    enable_parallel_search: bool = True
    enable_evaluation: bool = False
    eval_llm_provider: str = "openai"
    eval_llm_model: str = ""
    eval_embedding_model: str = ""
    eval_top_k: int = Field(default=3, gt=0)
    eval_fail_thresholds: dict = Field(default_factory=dict)
    llm_kwargs: dict = Field(default_factory=dict)

    @field_validator("retriever")
    @classmethod
    def validate_retriever(cls, value: str) -> str:
        if value not in {"tavily"}:
            raise ValueError("retriever must be one of: tavily")
        return value

    @field_validator("embedding_provider")
    @classmethod
    def validate_embedding_provider(cls, value: str) -> str:
        if value not in {"openai", "huggingface"}:
            raise ValueError("embedding_provider must be one of: openai, huggingface")
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        if value not in {"openai", "google"}:
            raise ValueError("llm_provider must be one of: openai, google")
        return value

    @field_validator("eval_llm_provider")
    @classmethod
    def validate_eval_llm_provider(cls, value: str) -> str:
        if value not in {"openai", "google"}:
            raise ValueError("eval_llm_provider must be one of: openai, google")
        return value


class Config:
    """ATLAS runtime configuration, layered from env vars, file, and mode.

    Values are first seeded from environment variables (with built-in
    defaults), then overlaid with ``config.json`` (or the file named by
    the ``CONFIG_FILE`` env var) via ``load_config_file()``, and validated
    against ``ConfigSchema``. Mode-specific overrides are layered on top
    afterward by calling ``apply_mode_config()``.
    """

    def __init__(self, config_file: str = None):
        """Seed config from env vars, then overlay and validate config_file.

        Args:
          config_file: Explicit path to a JSON config file. If omitted,
            falls back to the ``CONFIG_FILE`` env var, then ``config.json``.

        Raises:
          FileNotFoundError: If *config_file* (or ``CONFIG_FILE``) was
            explicitly specified but does not exist.
          ConfigError: If the resulting configuration fails validation,
            or required secrets are missing when ``REQUIRE_API_KEYS=true``.
        """
        # Use config.json by default if no config_file specified and no CONFIG_FILE env var
        env_config_file = os.getenv('CONFIG_FILE')
        self._config_file_explicit = config_file is not None or env_config_file is not None
        self.config_file = config_file if config_file else env_config_file or 'config.json'
        
        self.retriever = os.getenv('RETRIEVER', "tavily")
        self.embedding_provider = os.getenv('EMBEDDING_PROVIDER', "openai")
        self.llm_provider = os.getenv('LLM_PROVIDER', "openai")
        self.llm_model = os.getenv('LLM_MODEL', "gpt-4o-mini")
        
        # Token limit
        self.token_limit = int(os.getenv('TOKEN_LIMIT', 4000))
        self.browse_chunk_max_length = int(os.getenv('BROWSE_CHUNK_MAX_LENGTH', 8192))
        
        # Compression settings
        self.similarity_threshold = float(os.getenv('SIMILARITY_THRESHOLD', 0.55))
        self.chunk_size = int(os.getenv('CHUNK_SIZE', 500))
        self.chunk_overlap = int(os.getenv('CHUNK_OVERLAP', 100))
        
        # Research-optimized: More tokens for technical details
        self.summary_token_limit = int(os.getenv('SUMMARY_TOKEN_LIMIT', 1000))
        
        # Research-optimized: Lower temperature = more factual, less creative
        self.temperature = float(os.getenv('TEMPERATURE', 0.3))
        
        # User agent for web scraping
        self.user_agent = os.getenv('USER_AGENT', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                   "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0")
        
        # Research-optimized: More results = better paper coverage
        self.max_search_results_per_query = int(os.getenv('MAX_SEARCH_RESULTS_PER_QUERY', 8))
        
        # Memory and output settings
        self.memory_backend = os.getenv('MEMORY_BACKEND', "local")
        
        # Research-optimized: Longer reports for comprehensive analysis
        self.total_words = int(os.getenv('TOTAL_WORDS', 1500))
        self.report_format = os.getenv('REPORT_FORMAT', "APA")
        
        # Research-optimized: More iterations = more thorough research
        self.max_iterations = int(os.getenv('MAX_ITERATIONS', 4))
        self.agent_role = os.getenv('AGENT_ROLE', None)
        
        # Parallel search optimization: Enable parallel execution of multiple queries
        self.enable_parallel_search = os.getenv('ENABLE_PARALLEL_SEARCH', 'true').lower() == 'true'

        self.enable_evaluation = os.getenv('ENABLE_EVALUATION', 'false').lower() == 'true'
        self.eval_llm_provider = os.getenv('EVAL_LLM_PROVIDER', 'openai')
        self.eval_llm_model = os.getenv('EVAL_LLM_MODEL', '')
        self.eval_embedding_model = os.getenv('EVAL_EMBEDDING_MODEL', '')
        self.eval_top_k = int(os.getenv('EVAL_TOP_K', 3))
        self.eval_fail_thresholds = self._load_eval_thresholds(os.getenv('EVAL_FAIL_THRESHOLDS'))
        
        # Load config file FIRST (so mode configs can override it)
        self.load_config_file()
        if not hasattr(self, "llm_kwargs"):
            self.llm_kwargs = {}
        
        # Mode-specific configurations
        # Format: report_type -> config overrides
        # These will be applied AFTER config.json is loaded via apply_mode_config()
        # NOTE: Total sub-queries = max_iterations + 1 (original query is always added)
        self.mode_configs = MODE_CONFIGS
        self.validate()
        if os.getenv("REQUIRE_API_KEYS", "false").lower() == "true":
            self.validate_required_secrets()
    
    def apply_mode_config(self, report_type: str) -> None:
        """
        Apply mode-specific configuration overrides based on report type

        Args:
            report_type: The canonical mode id to configure for (see
                src.modes.registry).
        """
        from src.modes import get_mode_spec, is_known_mode

        if is_known_mode(report_type):
            spec = get_mode_spec(report_type)
            mode_config = self.mode_configs[spec.id]
            logger.info(f"Applying '{spec.id}' mode configuration (requested: '{report_type}')")

            # Actually apply the configuration values
            for key, value in mode_config.items():
                old_value = getattr(self, key, None)
                setattr(self, key, value)
                if old_value != value:
                    logger.info(f"  config override: {key}: {old_value} → {value}")
            self.validate()
            logger.info(spec.priority_note)
        else:
            logger.warning(f"No mode configuration found for '{report_type}', using defaults")
        
    def load_config_file(self) -> None:
        """Overlay values from ``self.config_file`` onto this instance.

        Silently does nothing if no config file is set, or if it's
        missing and was not explicitly requested (falls back to env-var
        defaults in that case).

        Raises:
          FileNotFoundError: If the config file was explicitly requested
            (via constructor arg or ``CONFIG_FILE`` env var) but doesn't
            exist on disk.
        """
        if self.config_file is None:
            return None
        if not os.path.exists(self.config_file):
            if self._config_file_explicit:
                raise FileNotFoundError(f"Config file not found: {self.config_file}")
            logger.info("Config file %s not found; using defaults and environment variables", self.config_file)
            return None
        with open(self.config_file, "r") as f:
            config = json.load(f)
        for key, value in config.items():
            self.__dict__[key] = value

    def _load_eval_thresholds(self, raw_value: str | None) -> dict:
        """Parse the ``EVAL_FAIL_THRESHOLDS`` JSON object, or return ``{}``."""
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ConfigError("EVAL_FAIL_THRESHOLDS must be a JSON object") from exc
        if not isinstance(parsed, dict):
            raise ConfigError("EVAL_FAIL_THRESHOLDS must be a JSON object")
        return parsed

    def validate(self) -> None:
        """Validate loaded environment and config-file values."""
        try:
            schema = ConfigSchema.model_validate(self.__dict__)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc

        for key, value in schema.model_dump().items():
            self.__dict__[key] = value

    def validate_required_secrets(self) -> None:
        """Fail fast when production secret requirements are not met."""
        required_env_vars = []
        if self.retriever == "tavily":
            required_env_vars.append("TAVILY_API_KEY")
        if self.embedding_provider == "openai":
            required_env_vars.append("OPENAI_API_KEY")
        if self.llm_provider == "openai":
            required_env_vars.append("OPENAI_API_KEY")
        if self.llm_provider == "google":
            required_env_vars.append("GEMINI_API_KEY")

        missing = sorted({key for key in required_env_vars if not os.getenv(key)})
        if missing:
            raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")
