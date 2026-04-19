from src.terminal.cpm_parser import CPMParser

def test_cpm_parser():
    # Mock CP/M DIR output based on App_Design.md examples
    mock_output = """
    C:
    TE       COM : WSCHANGE OVR : MYFILE   TXT
    
    C:  MOREFILES TXT : OTHER    BIN
    
    C>
    A: NO FILE FOUND
    D:  TEST     BIN : 
    """
    
    print("Testing CP/M Parser...")
    result = CPMParser.parse_dir_output(mock_output)
    
    expected = {
        "TE.COM": True,
        "WSCHANGE.OVR": True,
        "MYFILE.TXT": True,
        "MOREFILES.TXT": True,
        "OTHER.BIN": True,
        "TEST.BIN": True
    }
    
    assert result == expected
    print("✅ Test Passed!")

if __name__ == "__main__":
    try:
        test_cpm_parser()
    except AssertionError:
        print("❌ Test Failed!")
        import traceback
        traceback.print_exc()
