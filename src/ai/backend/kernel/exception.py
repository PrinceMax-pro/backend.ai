class MessageError(ValueError):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class DisallowedEnvironment(MessageError):
    pass


class DisallowedArgument(MessageError):
    pass


class InvalidServiceDefinition(MessageError):
    pass


class UnsupportedBaseDistroError(MessageError):
    pass


class InvalidServiceName(MessageError):
    pass
