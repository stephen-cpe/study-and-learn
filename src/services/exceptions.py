class StudyAndLearnError(Exception):
    pass


class AIServiceError(StudyAndLearnError):
    pass


class AIModelUnavailableError(AIServiceError):
    pass


class AICloudAPIError(AIServiceError):
    pass


class AITimeoutError(AIServiceError):
    pass
