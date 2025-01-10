from abc import ABC, abstractmethod
from financial_accounts.business.base_service import BaseService


class MatchingStrategy(ABC):
    @abstractmethod
    def match(self, candidate, target) -> bool:
        pass


class ExactMatchingStrategy(MatchingStrategy):
    def __init__(self, account, fields):
        self.account = account
        self.fields = fields

    def match(self, candidate, target) -> bool:
        for split in target.splits:
            if split.account == self.account:
                break
        else:
            return False

        for field in self.fields:
            left = getattr(candidate, field)
            right = getattr(target, field)
            if left != right:
                return False

        return True


class MatchingService(BaseService):
    def find_matching_transactions(self, candidate, batch, matching_strategy: MatchingStrategy):
        pass
