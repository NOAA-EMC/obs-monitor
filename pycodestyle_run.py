#!/usr/bin/env python

# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.

import unittest
import pycodestyle


# --------------------------------------------------------------------------------------------------


class TestCodeFormat(unittest.TestCase):

    def test_conformance(self):
        """Test that we conform to PEP-8."""
        style = pycodestyle.StyleGuide(config_file='pycodestyle.cfg')
        result = style.check_files(['.'])
        self.assertEqual(result.total_errors, 0, "Found code style errors (and warnings).")


# --------------------------------------------------------------------------------------------------


if __name__ == '__main__':
    unittest.main()
