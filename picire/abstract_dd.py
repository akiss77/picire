# Copyright (c) 2016-2020 Renata Hodovan, Akos Kiss.
#
# Licensed under the BSD 3-Clause License
# <LICENSE.rst or https://opensource.org/licenses/BSD-3-Clause>.
# This file may not be copied, modified, or distributed except
# according to those terms.

import itertools
import logging

from .outcome_cache import OutcomeCache

logger = logging.getLogger(__name__)


class AbstractDD(object):
    """
    Abstract super-class of the parallel and non-parallel DD classes.
    """

    # Test outcomes.
    PASS = 'PASS'
    FAIL = 'FAIL'

    def __init__(self, test, split, cache=None, id_prefix=()):
        """
        Initialise an abstract DD class. Not to be called directly, only by
        super calls in subclass initializers.

        :param test: A callable tester object.
        :param split: Splitter method to break a configuration up to n parts.
        :param cache: Cache object to use.
        :param id_prefix: Tuple to prepend to config IDs during tests.
        """
        self._test = test
        self._split = split
        self._cache = cache or OutcomeCache()
        self._id_prefix = id_prefix

    def ddmin(self, config, n=2):
        """
        Return a 1-minimal failing subset of the initial configuration.

        :param config: The initial configuration that will be reduced.
        :param n: The split ratio used to determine how many parts (subsets) the
            config to split to (both initially and later on whenever config
            subsets needs to be re-split).
        :return: 1-minimal failing configuration.
        """
        slices = []
        complement_offset = 0

        for run in itertools.count():
            assert self._test_config(config, ('r%d' % run, 'assert')) == self.FAIL

            # Minimization ends if the configuration is already reduced to a single unit.
            if len(config) < 2:
                logger.info('Done.')
                return config

            if len(slices) < 2:
                # This could be len(slices) == 1 but then we would need to initialize slices = [slice(0:len(config))]
                slices = self._split(len(config), min(len(config), n))

            logger.info('Run #%d: trying %s.', run, ' + '.join(str(s.stop - s.start) for s in slices))

            next_slices, complement_offset = self._reduce_config(run, config, slices, complement_offset)

            if next_slices is not None:
                # Interesting configuration is found, start new iteration.
                config = [c for s in next_slices for c in config[s]]
                slices = []
                start = 0
                for s in next_slices:
                    stop = start + s.stop - s.start
                    slices.append(slice(start, stop))
                    start = stop

                logger.info('Reduced to %d units.', len(config))
                logger.debug('New config: %r.', config)

            elif len(slices) < len(config):
                # No interesting configuration is found but it is still not the finest splitting, start new iteration.
                next_slices = self._split(len(config), min(len(config), len(slices) * n))
                complement_offset = (complement_offset * len(next_slices)) / len(slices)
                slices = next_slices

                logger.info('Increase granularity to %d.', len(slices))

            else:
                # Minimization ends if no interesting configuration was found by the finest splitting.
                logger.info('Done.')
                return config

    def _reduce_config(self, run, config, slices, complement_offset):
        """
        Perform the reduce task of ddmin. To be overridden by subclasses.

        :param run: The index of the current iteration.
        :param config: The current configuration under testing.
        :param slices: List of slices marking the boundaries of the sets that
            the current configuration is split to.
        :param complement_offset: A compensation offset needed to calculate the
            index of the first unchecked complement (optimization purpose only).
        :return: Tuple: (list of slices composing the failing config or None,
            next complement_offset).
        """
        raise NotImplementedError()

    def _lookup_cache(self, config, config_id):
        """
        Perform a cache lookup if caching is enabled.

        :param config: The configuration we are looking for.
        :param config_id: The ID describing the configuration (only for debug
            message).
        :return: None if outcome is not found for config in cache or if caching
            is disabled, PASS or FAIL otherwise.
        """
        cached_result = self._cache.lookup(config)
        if cached_result is not None:
            logger.debug('\t[ %s ]: cache = %r', self._pretty_config_id(self._id_prefix + config_id), cached_result)

        return cached_result

    def _test_config(self, config, config_id):
        """
        Test a single configuration and save the result in cache.

        :param config: The current configuration to test.
        :param config_id: Unique ID that will be used to save tests to easily
            identifiable directories.
        :return: PASS or FAIL
        """
        config_id = self._id_prefix + config_id

        logger.debug('\t[ %s ]: test...', self._pretty_config_id(config_id))
        outcome = self._test(config, config_id)
        logger.debug('\t[ %s ]: test = %r', self._pretty_config_id(config_id), outcome)

        if 'assert' not in config_id:
            self._cache.add(config, outcome)

        return outcome

    @staticmethod
    def _pretty_config_id(config_id):
        """
        Create beautified identifier for the current task from the argument.
        The argument is typically a tuple in the form of ('rN', 'DM'), where N
        is the index of the current iteration, D is direction of reduce (either
        s(ubset) or c(omplement)), and M is the index of the current test in the
        iteration. Alternatively, argument can also be in the form of
        (rN, 'assert') for double checking the input at the start of an
        iteration.

        :param config_id: Config ID tuple.
        :return: Concatenating the arguments with slashes, e.g., "rN / DM".
        """
        return ' / '.join(str(i) for i in config_id)

    @staticmethod
    def _minus(c1, c2):
        """
        Return a list of all elements of C1 that are not in C2.
        """
        c2 = set(c2)
        return [c for c in c1 if c not in c2]
